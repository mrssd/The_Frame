#!/usr/bin/env python3
"""
The Frame V2 — Main Entry Point
===============================
Portrait smart wall frame for Pimoroni Inky Impression 13.3" (1600 x 1200).

Stages:
  - Stage 1 (Morning Weather): Active between MORNING_START_HOUR and MORNING_END_HOUR
    (default 7:00 AM – 10:00 AM, configured in .env).
  - Stage 2 (Dynamic Photo Frame): Active outside the morning weather window;
    randomly rotates uploaded photos once per day, managed via the local
    passcode-protected web portal (http://<pi-ip>:8080).

Usage:
  python main.py                             # Run scheduler + local web portal
  python main.py --once                      # Run one stage cycle and exit
  python main.py --stage weather --force --once
  python main.py --stage photo --force --once
  python main.py --mock --once               # Render preview PNG without hardware
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from config import Config
from display import FrameDisplay
from photos import PhotoLibrary
from portal import PhotoPortalServer
from stages.morning_weather import render_morning_weather
from stages.photo_frame import render_photo_frame
from weather import WeatherService

logger = logging.getLogger("frame_v2")


def _setup_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


def is_morning_window(now: datetime, config: Config) -> bool:
    """Return True when current local time is within [MORNING_START_HOUR, MORNING_END_HOUR)."""
    return config.morning_start_hour <= now.hour < config.morning_end_hour


class FrameV2App:
    """Stage-based controller for The Frame V2."""

    def __init__(self, config: Config, force_mock: bool = False) -> None:
        self.config = config
        self.tz = ZoneInfo(config.timezone)
        self.display = FrameDisplay(config, force_mock=force_mock)
        self.weather = WeatherService(config)
        self.photos = PhotoLibrary(config)

        self._active_stage: str | None = None
        self._last_weather_push: datetime | None = None
        self._last_photo_shown: str | None = None
        self._last_photo_date: str | None = None

        self.portal: PhotoPortalServer | None = None
        if config.portal_enabled:
            self.portal = PhotoPortalServer(
                config=config,
                library=self.photos,
                on_show_photo=self.show_specific_photo,
                on_rotate_random=self.rotate_random_now,
                on_config_reloaded=self.reload_config,
                on_refresh_display=self.refresh_display_now,
            )

    def reload_config(self) -> Config:
        """Reload .env from disk and propagate updated settings to all components."""
        new_cfg = Config.load(env_path=self.config.env_path, override=True)
        self.config = new_cfg
        self.tz = ZoneInfo(new_cfg.timezone)
        self.display.config = new_cfg
        self.weather.config = new_cfg
        self.photos.config = new_cfg
        if self.portal is not None:
            self.portal.config = new_cfg
            self.portal.auth.update_passcode(new_cfg.portal_passcode)
        logger.info("Reloaded .env configuration live.")
        return new_cfg

    def refresh_display_now(self) -> None:
        """Force an immediate re-render of the currently active stage."""
        threading.Thread(
            target=self.run_cycle, kwargs={"force": True}, daemon=True
        ).start()

    # ── Stage 1: Morning Weather ──────────────────────────────────────────────

    def _run_weather_stage(self, now: datetime, force: bool = False) -> bool:
        min_interval = timedelta(minutes=self.config.refresh_interval_minutes)
        entering_stage = self._active_stage != "weather"

        if not force and not entering_stage and self._last_weather_push is not None:
            elapsed = now - self._last_weather_push
            if elapsed < min_interval:
                return False

        snapshot = self.weather.get_weather()
        if snapshot is None:
            logger.error("No weather data available (live or cached); skipping refresh.")
            return False

        image = render_morning_weather(
            weather=snapshot,
            config=self.config,
            now=now,
            canvas_size=self.display.canvas_size,
        )
        self.display.push(image)
        self._active_stage = "weather"
        self._last_weather_push = now
        return True

    # ── Stage 2: Dynamic Photo Frame ──────────────────────────────────────────

    def _run_photo_stage(self, now: datetime, force: bool = False, force_new_photo: bool = False) -> bool:
        today_str = now.strftime("%Y-%m-%d")
        photo_path = self.photos.get_photo_for_today(now, force_new=force_new_photo)
        photo_name = photo_path.name if photo_path else None

        entering_stage = self._active_stage != "photo"
        photo_changed = (photo_name != self._last_photo_shown) or (today_str != self._last_photo_date)

        if not force and not entering_stage and not photo_changed:
            return False

        image = render_photo_frame(
            photo_path=photo_path,
            config=self.config,
            canvas_size=self.display.canvas_size,
        )
        self.display.push(image)
        self._active_stage = "photo"
        self._last_photo_shown = photo_name
        self._last_photo_date = today_str
        return True

    # ── Portal callbacks ──────────────────────────────────────────────────────

    def show_specific_photo(self, filename: str) -> None:
        """Immediately display a chosen photo from the web portal."""
        now = datetime.now(tz=self.tz)
        photo_path = self.photos.set_current_photo(filename, now)
        if photo_path is None:
            return
        image = render_photo_frame(
            photo_path=photo_path,
            config=self.config,
            canvas_size=self.display.canvas_size,
        )
        self.display.push(image)
        self._active_stage = "photo"
        self._last_photo_shown = photo_path.name
        self._last_photo_date = now.strftime("%Y-%m-%d")

    def rotate_random_now(self) -> str | None:
        """Pick a new random photo and push it to the display asynchronously."""
        now = datetime.now(tz=self.tz)
        photo_path = self.photos.get_photo_for_today(now, force_new=True)
        if photo_path is None:
            return None

        def _push() -> None:
            image = render_photo_frame(
                photo_path=photo_path,
                config=self.config,
                canvas_size=self.display.canvas_size,
            )
            self.display.push(image)
            self._active_stage = "photo"
            self._last_photo_shown = photo_path.name
            self._last_photo_date = now.strftime("%Y-%m-%d")

        threading.Thread(target=_push, daemon=True).start()
        return photo_path.name

    # ── Scheduler loop ────────────────────────────────────────────────────────

    def run_cycle(self, force: bool = False, stage_override: str | None = None) -> bool:
        now = datetime.now(tz=self.tz)
        if stage_override == "weather":
            return self._run_weather_stage(now, force=True)
        if stage_override == "photo":
            return self._run_photo_stage(now, force=True)

        if is_morning_window(now, self.config):
            return self._run_weather_stage(now, force=force)
        return self._run_photo_stage(now, force=force)

    def run_forever(self, force_first: bool = False, stage_override: str | None = None) -> None:
        if self.portal is not None:
            self.portal.start()

        logger.info(
            "The Frame V2 started | Portrait %dx%d | Weather %02d:00–%02d:00 | Photos otherwise (%s)",
            self.display.canvas_size[0],
            self.display.canvas_size[1],
            self.config.morning_start_hour,
            self.config.morning_end_hour,
            self.config.timezone,
        )
        try:
            first = True
            while True:
                self.run_cycle(
                    force=(force_first and first),
                    stage_override=(stage_override if first else None),
                )
                first = False
                time.sleep(self.config.check_interval_seconds)
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
        finally:
            if self.portal is not None:
                self.portal.stop()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="The Frame V2 — Morning Weather + Dynamic Photo Frame")
    parser.add_argument("--env", type=Path, help="Path to custom .env file")
    parser.add_argument("--mock", action="store_true", help="Render PNG preview instead of pushing to hardware")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--force", action="store_true", help="Force immediate display refresh")
    parser.add_argument(
        "--stage",
        choices=("weather", "photo"),
        help="Force a specific stage (weather or photo) regardless of time of day",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    config = Config.load(env_path=args.env)
    _setup_logging(config.log_level)

    app = FrameV2App(config, force_mock=args.mock)
    if args.once:
        app.run_cycle(force=args.force, stage_override=args.stage)
    else:
        app.run_forever(force_first=args.force, stage_override=args.stage)


if __name__ == "__main__":
    main()
