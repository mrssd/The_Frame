"""Open-Meteo weather client, condition-image mapping, and disk cache."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import Config

logger = logging.getLogger(__name__)

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT_SECONDS = 25

# WMO Weather Code -> (Human-readable label, image filename in conditions/)
# Filenames match the exact assets in The_Frame_V2/conditions/
WMO_CONDITION_MAP: dict[int, tuple[str, str]] = {
    0:  ("Sunny", "sunny.JPG"),
    1:  ("Mainly Clear", "sunny.JPG"),
    2:  ("Partly Cloudy", "partialy_cloudy.JPG"),
    3:  ("Cloudy", "cloudyJPG.JPG"),
    45: ("Foggy", "foggy.JPG"),
    48: ("Icy Fog", "foggy.JPG"),
    51: ("Light Drizzle", "rainy.JPG"),
    53: ("Drizzle", "rainy.JPG"),
    55: ("Heavy Drizzle", "rainy.JPG"),
    56: ("Freezing Drizzle", "rainy.JPG"),
    57: ("Freezing Drizzle", "rainy.JPG"),
    61: ("Light Rain", "rainy.JPG"),
    63: ("Rain", "rainy.JPG"),
    65: ("Heavy Rain", "shower.JPG"),
    66: ("Freezing Rain", "rainy.JPG"),
    67: ("Heavy Freezing Rain", "shower.JPG"),
    71: ("Light Snow", "snowy.JPG"),
    73: ("Snow", "snowy.JPG"),
    75: ("Heavy Snow", "snowy.JPG"),
    77: ("Snow Grains", "snowy.JPG"),
    80: ("Rain Showers", "shower.JPG"),
    81: ("Rain Showers", "shower.JPG"),
    82: ("Heavy Showers", "shower.JPG"),
    85: ("Snow Showers", "snowy.JPG"),
    86: ("Heavy Snow Showers", "snowy.JPG"),
    95: ("Thunderstorm", "thunderstorm.JPG"),
    96: ("Thunderstorm", "thunderstorm.JPG"),
    99: ("Severe Thunderstorm", "thunderstorm.JPG"),
}


def decode_wmo(code: int) -> tuple[str, str]:
    """Return (condition_label, image_filename) for a WMO weather code."""
    return WMO_CONDITION_MAP.get(code, ("Overcast", "drak_cloud.JPG"))


@dataclass
class WeatherSnapshot:
    fetched_at: str
    weather_code: int
    condition: str
    image_filename: str
    temperature: float
    temp_unit: str
    rain_chance: int          # 0..100 (%)
    today_high: float
    today_low: float

    @property
    def degree_text(self) -> str:
        return f"{round(self.temperature)}°"

    @property
    def high_low_text(self) -> str:
        return f"H {round(self.today_high)}°   ·   L {round(self.today_low)}°"


class WeatherService:
    """Fetches current weather + rain probability from Open-Meteo with JSON cache fallback."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.cache_file: Path = config.cache_dir / "weather_cache.json"

    def fetch(self) -> WeatherSnapshot:
        temp_unit_param = "fahrenheit" if self.config.temp_unit == "F" else "celsius"
        params = {
            "latitude": self.config.latitude,
            "longitude": self.config.longitude,
            "timezone": self.config.timezone,
            "temperature_unit": temp_unit_param,
            "current": "temperature_2m,precipitation_probability,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "forecast_days": 1,
        }

        logger.info(
            "Fetching Open-Meteo weather for %.4f, %.4f (%s)",
            self.config.latitude,
            self.config.longitude,
            self.config.location_name,
        )
        resp = requests.get(_OPEN_METEO_URL, params=params, timeout=_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()

        current = data.get("current", {})
        daily = data.get("daily", {})

        wmo_code = int(current.get("weather_code", 3))
        condition, image_filename = decode_wmo(wmo_code)

        # Prefer current precipitation_probability; fall back to daily max if unavailable
        cur_prob = current.get("precipitation_probability")
        daily_probs = daily.get("precipitation_probability_max") or [0]
        if cur_prob is None:
            rain_chance = int(daily_probs[0] or 0)
        else:
            # Show the higher of current vs today's morning/daily max so users aren't caught off-guard
            rain_chance = max(int(cur_prob), int(daily_probs[0] or 0))

        high = float((daily.get("temperature_2m_max") or [0])[0] or 0)
        low = float((daily.get("temperature_2m_min") or [0])[0] or 0)

        snapshot = WeatherSnapshot(
            fetched_at=datetime.now(tz=timezone.utc).isoformat(),
            weather_code=wmo_code,
            condition=condition,
            image_filename=image_filename,
            temperature=float(current.get("temperature_2m", 0)),
            temp_unit=self.config.temp_unit,
            rain_chance=max(0, min(100, rain_chance)),
            today_high=high,
            today_low=low,
        )
        self._save_cache(snapshot)
        logger.info(
            "Weather: %s | %s%s | Rain %d%% | Image: %s",
            snapshot.condition,
            snapshot.degree_text,
            snapshot.temp_unit,
            snapshot.rain_chance,
            snapshot.image_filename,
        )
        return snapshot

    def get_weather(self) -> WeatherSnapshot | None:
        """Fetch live weather, falling back to cached snapshot on network failure."""
        try:
            return self.fetch()
        except Exception as exc:
            logger.error("Weather fetch failed: %s — trying cache", exc)
            return self.load_cache()

    def _save_cache(self, snapshot: WeatherSnapshot) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(json.dumps(asdict(snapshot), indent=2), encoding="utf-8")

    def load_cache(self) -> WeatherSnapshot | None:
        if not self.cache_file.exists():
            return None
        try:
            raw = json.loads(self.cache_file.read_text(encoding="utf-8"))
            return WeatherSnapshot(**raw)
        except Exception as exc:
            logger.warning("Failed to load weather cache: %s", exc)
            return None
