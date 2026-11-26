"""Photo library management, thumbnail generation, and daily random rotation."""

from __future__ import annotations

import io
import json
import logging
import random
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from config import Config

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


@dataclass
class PhotoItem:
    filename: str
    path: Path
    size_bytes: int
    modified_ts: float
    is_current: bool = False


class PhotoLibrary:
    """Thread-safe photo store with daily random rotation state."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.photos_dir = config.photos_dir
        self.thumbs_dir = config.cache_dir / "thumbs"
        self.state_file = config.cache_dir / "photo_state.json"
        self._lock = threading.RLock()

        self.photos_dir.mkdir(parents=True, exist_ok=True)
        self.thumbs_dir.mkdir(parents=True, exist_ok=True)

    # ── Photo listing & lookup ────────────────────────────────────────────────

    def list_photos(self) -> list[PhotoItem]:
        with self._lock:
            state = self._load_state()
            current_name = state.get("current_photo")
            items: list[PhotoItem] = []

            for p in self.photos_dir.iterdir():
                if not p.is_file():
                    continue
                if p.name.startswith(".") or p.name.startswith("._"):
                    continue
                if p.suffix.lower() not in ALLOWED_EXTENSIONS:
                    continue
                stat = p.stat()
                items.append(
                    PhotoItem(
                        filename=p.name,
                        path=p,
                        size_bytes=stat.st_size,
                        modified_ts=stat.st_mtime,
                        is_current=(p.name == current_name),
                    )
                )

            items.sort(key=lambda x: x.modified_ts, reverse=True)
            return items

    def get_photo_path(self, filename: str) -> Path | None:
        """Safely resolve a photo filename inside photos_dir (prevents path traversal)."""
        safe_name = Path(filename).name
        if safe_name != filename or safe_name.startswith("."):
            return None
        target = (self.photos_dir / safe_name).resolve()
        try:
            target.relative_to(self.photos_dir.resolve())
        except ValueError:
            return None
        return target if target.is_file() else None

    def get_thumbnail_bytes(self, filename: str) -> bytes | None:
        """Return JPEG thumbnail bytes (360x480 max) for fast portal gallery loading."""
        photo_path = self.get_photo_path(filename)
        if photo_path is None:
            return None

        thumb_path = self.thumbs_dir / f"{photo_path.stem}.jpg"
        try:
            if thumb_path.exists() and thumb_path.stat().st_mtime >= photo_path.stat().st_mtime:
                return thumb_path.read_bytes()

            with Image.open(photo_path) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((420, 560), Image.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=82)
                data = buf.getvalue()
                thumb_path.write_bytes(data)
                return data
        except Exception as exc:
            logger.warning("Failed to generate thumbnail for %s: %s", filename, exc)
            return None

    # ── Upload & delete ───────────────────────────────────────────────────────

    def save_upload(self, original_name: str, raw_bytes: bytes) -> PhotoItem:
        """Validate, normalize EXIF orientation, and store an uploaded photo."""
        if not raw_bytes:
            raise ValueError("Empty upload")
        if len(raw_bytes) > MAX_UPLOAD_BYTES:
            raise ValueError("File exceeds 25 MB limit")

        # Validate it's a real image and normalize orientation + RGB
        try:
            with Image.open(io.BytesIO(raw_bytes)) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                # Cap absurdly huge phone camera resolutions to save Pi SD card & RAM
                if max(im.size) > 2400:
                    im.thumbnail((2400, 2400), Image.LANCZOS)

                stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(original_name).stem).strip("_")[:40]
                if not stem:
                    stem = "photo"
                unique_name = f"{stem}_{uuid.uuid4().hex[:6]}.jpg"
                dest = self.photos_dir / unique_name

                with self._lock:
                    im.save(dest, format="JPEG", quality=92)
                    stat = dest.stat()
                    logger.info("Saved uploaded photo: %s (%d bytes)", unique_name, stat.st_size)
                    return PhotoItem(
                        filename=unique_name,
                        path=dest,
                        size_bytes=stat.st_size,
                        modified_ts=stat.st_mtime,
                        is_current=False,
                    )
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Unsupported or invalid image file: {exc}") from exc

    def delete_photo(self, filename: str) -> bool:
        """Delete a photo and its thumbnail; clear current_photo if it was active."""
        with self._lock:
            target = self.get_photo_path(filename)
            if target is None:
                return False

            target.unlink(missing_ok=True)
            thumb = self.thumbs_dir / f"{target.stem}.jpg"
            thumb.unlink(missing_ok=True)

            state = self._load_state()
            if state.get("current_photo") == filename:
                state["current_photo"] = None
                self._save_state(state)

            logger.info("Deleted photo: %s", filename)
            return True

    # ── Daily random rotation ─────────────────────────────────────────────────

    def get_photo_for_today(self, now: datetime, force_new: bool = False) -> Path | None:
        """
        Return the photo to display today.
        Automatically picks a new random photo once per calendar day (avoiding repeats
        until all photos have been shown), or immediately if force_new=True or the
        active photo was deleted.
        """
        with self._lock:
            items = self.list_photos()
            if not items:
                return None

            available_names = [i.filename for i in items]
            today_str = now.strftime("%Y-%m-%d")
            state = self._load_state()

            current = state.get("current_photo")
            last_date = state.get("date")

            if (
                not force_new
                and last_date == today_str
                and current in available_names
            ):
                return self.photos_dir / current

            # Pick a random photo not recently shown
            shown: list[str] = [n for n in state.get("shown_cycle", []) if n in available_names]
            candidates = [n for n in available_names if n not in shown and n != current]
            if not candidates:
                # Completed full cycle — reset cycle, still avoid immediate repeat if >1 photo
                shown = []
                candidates = [n for n in available_names if n != current] or available_names

            chosen = random.choice(candidates)
            shown.append(chosen)

            state["date"] = today_str
            state["current_photo"] = chosen
            state["shown_cycle"] = shown
            self._save_state(state)

            logger.info("Selected daily photo for %s: %s", today_str, chosen)
            return self.photos_dir / chosen

    def set_current_photo(self, filename: str, now: datetime) -> Path | None:
        """Explicitly set a specific photo as today's active photo (e.g. 'Show Now')."""
        with self._lock:
            target = self.get_photo_path(filename)
            if target is None:
                return None

            state = self._load_state()
            state["date"] = now.strftime("%Y-%m-%d")
            state["current_photo"] = filename
            shown = list(state.get("shown_cycle", []))
            if filename not in shown:
                shown.append(filename)
            state["shown_cycle"] = shown
            self._save_state(state)
            logger.info("Manually set active photo: %s", filename)
            return target

    def get_current_photo_name(self) -> str | None:
        with self._lock:
            return self._load_state().get("current_photo")

    # ── State persistence ─────────────────────────────────────────────────────

    def _load_state(self) -> dict:
        if not self.state_file.exists():
            return {}
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self, state: dict) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
