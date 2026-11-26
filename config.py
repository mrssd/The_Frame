"""Configuration loader for The Frame V2 (reads from .env)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Settings exposed in the web portal Settings tab
PORTAL_SETTINGS_SCHEMA: list[dict] = [
    # Location & Weather
    {"key": "LOCATION_NAME", "label": "City / Location Name", "group": "Weather & Location", "type": "text"},
    {"key": "LATITUDE", "label": "Latitude", "group": "Weather & Location", "type": "number", "step": "any"},
    {"key": "LONGITUDE", "label": "Longitude", "group": "Weather & Location", "type": "number", "step": "any"},
    {"key": "TIMEZONE", "label": "Timezone (IANA)", "group": "Weather & Location", "type": "text"},
    {"key": "TEMP_UNIT", "label": "Temperature Unit", "group": "Weather & Location", "type": "select", "options": ["C", "F"]},

    # Schedule
    {"key": "MORNING_START_HOUR", "label": "Morning Weather Start Hour (0–23)", "group": "Schedule", "type": "number", "min": 0, "max": 23, "step": 1},
    {"key": "MORNING_END_HOUR", "label": "Morning Weather End Hour (0–24)", "group": "Schedule", "type": "number", "min": 0, "max": 24, "step": 1},
    {"key": "REFRESH_INTERVAL_MINUTES", "label": "Weather Refresh Interval (min)", "group": "Schedule", "type": "number", "min": 5, "max": 180, "step": 1},

    # Photo & Display
    {"key": "PHOTO_FIT_MODE", "label": "Photo Fit Mode", "group": "Photo & Display", "type": "select", "options": ["resize", "cover", "contain"]},
    {"key": "PHOTO_MAT_BORDER", "label": "White Mat Border (px)", "group": "Photo & Display", "type": "number", "min": 0, "max": 200, "step": 5},
    {"key": "DISPLAY_ROTATION", "label": "Portrait Rotation (deg)", "group": "Photo & Display", "type": "select", "options": ["90", "270"]},
    {"key": "DISPLAY_SATURATION", "label": "E-Ink Saturation (0.0–1.0)", "group": "Photo & Display", "type": "number", "min": 0, "max": 1, "step": 0.05},
    {"key": "PHOTO_CONTRAST", "label": "Photo Contrast", "group": "Photo & Display", "type": "number", "min": 0.5, "max": 2.5, "step": 0.05},
    {"key": "PHOTO_COLOR_BOOST", "label": "Photo Color Boost", "group": "Photo & Display", "type": "number", "min": 0.5, "max": 2.5, "step": 0.05},
    {"key": "PHOTO_SHARPNESS", "label": "Photo Sharpness", "group": "Photo & Display", "type": "number", "min": 0.5, "max": 2.5, "step": 0.05},

    # Weather Sketch
    {"key": "SKETCH_GAMMA", "label": "Weather Sketch Darkening (Gamma)", "group": "Weather Sketch", "type": "number", "min": 0.8, "max": 3.5, "step": 0.1},
    {"key": "SKETCH_CONTRAST", "label": "Weather Sketch Contrast", "group": "Weather Sketch", "type": "number", "min": 0.5, "max": 3.0, "step": 0.05},
    {"key": "SKETCH_COLOR_BOOST", "label": "Weather Sketch Color Boost", "group": "Weather Sketch", "type": "number", "min": 0.5, "max": 3.0, "step": 0.05},
    {"key": "SKETCH_SHARPNESS", "label": "Weather Sketch Sharpness", "group": "Weather Sketch", "type": "number", "min": 0.5, "max": 3.0, "step": 0.05},

    # Security
    {"key": "PORTAL_PASSCODE", "label": "Portal Passcode", "group": "Portal Security", "type": "text"},
]

EDITABLE_ENV_KEYS: set[str] = {item["key"] for item in PORTAL_SETTINGS_SCHEMA}


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    return int(val.strip())


def _get_float(key: str, default: float) -> float:
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    return float(val.strip())


@dataclass(frozen=True)
class Config:
    # Location & weather
    location_name: str
    latitude: float
    longitude: float
    timezone: str
    temp_unit: str  # "C" or "F"

    # Schedule
    morning_start_hour: int
    morning_end_hour: int
    refresh_interval_minutes: int
    check_interval_seconds: int

    # Display
    display_orientation: str
    display_rotation: int
    display_width: int
    display_height: int
    display_saturation: float
    sketch_contrast: float
    sketch_color_boost: float
    sketch_sharpness: float
    sketch_gamma: float
    mock_mode: bool
    mock_output_path: Path

    # Paths
    conditions_dir: Path
    photos_dir: Path
    cache_dir: Path
    font_bold_path: str
    font_regular_path: str

    # Stage 2: Photo Frame & Web Portal
    portal_enabled: bool
    portal_host: str
    portal_port: int
    portal_passcode: str
    photo_fit_mode: str  # "cover" or "contain"
    photo_mat_border: int
    photo_contrast: float
    photo_color_boost: float
    photo_sharpness: float

    # Logging
    log_level: str

    # Source .env path
    env_path: Path

    @classmethod
    def load(cls, env_path: Path | None = None, override: bool = False) -> "Config":
        dotenv_file = (env_path or (BASE_DIR / ".env")).resolve()
        load_dotenv(dotenv_file, override=override)

        def _resolve(rel_or_abs: str) -> Path:
            p = Path(rel_or_abs)
            return p if p.is_absolute() else (BASE_DIR / p)

        unit = os.getenv("TEMP_UNIT", "C").strip().upper()
        if unit not in ("C", "F"):
            unit = "C"

        return cls(
            location_name=os.getenv("LOCATION_NAME", "Vancouver, BC").strip(),
            latitude=_get_float("LATITUDE", 49.260665),
            longitude=_get_float("LONGITUDE", -123.213458),
            timezone=os.getenv("TIMEZONE", "America/Vancouver").strip(),
            temp_unit=unit,
            morning_start_hour=_get_int("MORNING_START_HOUR", 7),
            morning_end_hour=_get_int("MORNING_END_HOUR", 10),
            refresh_interval_minutes=_get_int("REFRESH_INTERVAL_MINUTES", 30),
            check_interval_seconds=_get_int("CHECK_INTERVAL_SECONDS", 60),
            display_orientation=os.getenv("DISPLAY_ORIENTATION", "portrait").strip().lower(),
            display_rotation=_get_int("DISPLAY_ROTATION", 90),
            display_width=_get_int("DISPLAY_WIDTH", 1200),
            display_height=_get_int("DISPLAY_HEIGHT", 1600),
            display_saturation=_get_float("DISPLAY_SATURATION", 0.5),
            sketch_contrast=_get_float("SKETCH_CONTRAST", 1.40),
            sketch_color_boost=_get_float("SKETCH_COLOR_BOOST", 1.85),
            sketch_sharpness=_get_float("SKETCH_SHARPNESS", 1.30),
            sketch_gamma=_get_float("SKETCH_GAMMA", 2.20),
            mock_mode=_get_bool("MOCK_MODE", False),
            mock_output_path=_resolve(os.getenv("MOCK_OUTPUT_PATH", "cache/preview.png")),
            conditions_dir=_resolve(os.getenv("CONDITIONS_DIR", "conditions")),
            photos_dir=_resolve(os.getenv("PHOTOS_DIR", "photos")),
            cache_dir=_resolve(os.getenv("CACHE_DIR", "cache")),
            font_bold_path=os.getenv("FONT_BOLD_PATH", "").strip(),
            font_regular_path=os.getenv("FONT_REGULAR_PATH", "").strip(),
            portal_enabled=_get_bool("PORTAL_ENABLED", True),
            portal_host=os.getenv("PORTAL_HOST", "0.0.0.0").strip(),
            portal_port=_get_int("PORTAL_PORT", 8080),
            portal_passcode=os.getenv("PORTAL_PASSCODE", "1234").strip(),
            photo_fit_mode=os.getenv("PHOTO_FIT_MODE", "resize").strip().lower(),
            photo_mat_border=_get_int("PHOTO_MAT_BORDER", 0),
            photo_contrast=_get_float("PHOTO_CONTRAST", 1.10),
            photo_color_boost=_get_float("PHOTO_COLOR_BOOST", 1.15),
            photo_sharpness=_get_float("PHOTO_SHARPNESS", 1.10),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            env_path=dotenv_file,
        )

    def to_editable_dict(self) -> dict[str, str]:
        """Return current values for all portal-editable .env keys."""
        return {
            "LOCATION_NAME": self.location_name,
            "LATITUDE": str(self.latitude),
            "LONGITUDE": str(self.longitude),
            "TIMEZONE": self.timezone,
            "TEMP_UNIT": self.temp_unit,
            "MORNING_START_HOUR": str(self.morning_start_hour),
            "MORNING_END_HOUR": str(self.morning_end_hour),
            "REFRESH_INTERVAL_MINUTES": str(self.refresh_interval_minutes),
            "PHOTO_FIT_MODE": self.photo_fit_mode,
            "PHOTO_MAT_BORDER": str(self.photo_mat_border),
            "DISPLAY_ROTATION": str(self.display_rotation),
            "DISPLAY_SATURATION": str(self.display_saturation),
            "PHOTO_CONTRAST": str(self.photo_contrast),
            "PHOTO_COLOR_BOOST": str(self.photo_color_boost),
            "PHOTO_SHARPNESS": str(self.photo_sharpness),
            "SKETCH_GAMMA": str(self.sketch_gamma),
            "SKETCH_CONTRAST": str(self.sketch_contrast),
            "SKETCH_COLOR_BOOST": str(self.sketch_color_boost),
            "SKETCH_SHARPNESS": str(self.sketch_sharpness),
            "PORTAL_PASSCODE": self.portal_passcode,
        }


def update_env_file(env_path: Path, updates: dict[str, str]) -> dict[str, str]:
    """
    Update allowed keys in the .env file in-place while preserving comments & formatting.
    Returns the sanitized dictionary of applied updates.
    """
    clean: dict[str, str] = {}
    for k, v in updates.items():
        if k not in EDITABLE_ENV_KEYS:
            continue
        val_str = str(v).replace("\r", "").replace("\n", "").strip()
        if k == "PORTAL_PASSCODE" and not val_str:
            raise ValueError("Passcode cannot be empty")
        if k in ("MORNING_START_HOUR", "MORNING_END_HOUR", "REFRESH_INTERVAL_MINUTES", "PHOTO_MAT_BORDER", "DISPLAY_ROTATION"):
            int(val_str)  # validate integer
        if k in ("LATITUDE", "LONGITUDE", "DISPLAY_SATURATION", "PHOTO_CONTRAST", "PHOTO_COLOR_BOOST", "PHOTO_SHARPNESS", "SKETCH_GAMMA", "SKETCH_CONTRAST", "SKETCH_COLOR_BOOST", "SKETCH_SHARPNESS"):
            float(val_str)  # validate float
        if k == "TEMP_UNIT" and val_str.upper() not in ("C", "F"):
            raise ValueError("TEMP_UNIT must be C or F")
        if k == "PHOTO_FIT_MODE" and val_str.lower() not in ("resize", "cover", "contain"):
            raise ValueError("PHOTO_FIT_MODE must be resize, cover, or contain")
        clean[k] = val_str

    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    remaining = dict(clean)
    out_lines: list[str] = []

    key_pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
    for line in lines:
        m = key_pattern.match(line)
        if m and m.group(1) in remaining:
            key = m.group(1)
            out_lines.append(f"{key}={remaining.pop(key)}")
        else:
            out_lines.append(line)

    if remaining:
        if out_lines and out_lines[-1].strip() != "":
            out_lines.append("")
        for key, val in remaining.items():
            out_lines.append(f"{key}={val}")

    env_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return clean
