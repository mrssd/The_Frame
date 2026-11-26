"""Display driver for Inky Impression 13.3" (Spectra 6) in portrait mode + mock PNG mode."""

from __future__ import annotations

import logging
import threading
from PIL import Image

from config import Config

logger = logging.getLogger(__name__)


class FrameDisplay:
    """Handles portrait canvas sizing, hardware rotation, and mock PNG output."""

    def __init__(self, config: Config, force_mock: bool = False) -> None:
        self.config = config
        self.mock_mode = force_mock or config.mock_mode
        self._inky = None
        self._lock = threading.Lock()

        if not self.mock_mode:
            self._init_hardware()
        else:
            logger.info("Display running in MOCK mode (PNG output only)")

    @property
    def canvas_size(self) -> tuple[int, int]:
        """Return (width, height) of the logical portrait canvas (default 1200x1600)."""
        if self._inky is not None:
            w, h = self._inky.width, self._inky.height
        else:
            w, h = self.config.display_width, self.config.display_height

        if self.config.display_orientation == "portrait":
            return (min(w, h), max(w, h))
        return (max(w, h), min(w, h))

    def _init_hardware(self) -> None:
        try:
            from inky.auto import auto  # type: ignore[import]
            self._inky = auto(ask_user=True, verbose=True)
            logger.info(
                "Detected Inky display: %dx%d",
                self._inky.width,
                self._inky.height,
            )
        except Exception as exc:
            logger.error("Could not initialize Inky hardware: %s", exc)
            logger.warning("Falling back to mock PNG mode")
            self.mock_mode = True

    def push(self, image: Image.Image) -> None:
        """Push a portrait (1200x1600) RGB image to the Inky display or save mock PNG."""
        with self._lock:
            self._push_unlocked(image)

    def _push_unlocked(self, image: Image.Image) -> None:
        if self.mock_mode or self._inky is None:
            out_path = self.config.mock_output_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(out_path)
            logger.info("Saved mock preview -> %s (%dx%d)", out_path, image.width, image.height)
            return

        hw_w, hw_h = self._inky.width, self._inky.height
        out = image

        # Rotate portrait canvas (1200x1600) to landscape-native panel (1600x1200)
        if self.config.display_orientation == "portrait" and hw_w > hw_h:
            rot = self.config.display_rotation % 360
            if rot == 90:
                out = image.transpose(Image.ROTATE_90)
            elif rot == 270:
                out = image.transpose(Image.ROTATE_270)
            elif rot == 180:
                out = image.transpose(Image.ROTATE_180)

        if out.size != (hw_w, hw_h):
            out = out.resize((hw_w, hw_h), Image.LANCZOS)

        try:
            self._inky.set_image(out, saturation=self.config.display_saturation)
        except TypeError:
            self._inky.set_image(out)

        logger.info("Refreshing Inky Impression (%dx%d)...", hw_w, hw_h)
        self._inky.show()
        logger.info("Display refresh complete.")
