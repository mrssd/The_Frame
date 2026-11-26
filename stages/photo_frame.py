"""
Stage 2 — Dynamic Photo Frame Renderer (Portrait 1200 x 1600).

Renders uploaded photos onto the portrait E-Ink canvas with:
  - Automatic EXIF orientation handling
  - Configurable fit mode:
      * "cover"   — fills the entire 1200x1600 portrait frame edge-to-edge (center-cropped)
      * "contain" — fits the full photo inside a clean white museum mat
  - Subtle contrast/color/sharpness tuning for E-Ink Spectra 6
  - Clean museum-styled placeholder screen when no photos have been uploaded yet
"""

from __future__ import annotations

import logging
import socket
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from config import Config
from stages.morning_weather import BG_WHITE, INK_DARK, INK_MUTED, _load_font

logger = logging.getLogger(__name__)


def _get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "raspberrypi.local"


def _enhance_photo(img: Image.Image, config: Config) -> Image.Image:
    if config.photo_contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(config.photo_contrast)
    if config.photo_color_boost != 1.0:
        img = ImageEnhance.Color(img).enhance(config.photo_color_boost)
    if config.photo_sharpness != 1.0:
        img = ImageEnhance.Sharpness(img).enhance(config.photo_sharpness)
    return img


def render_photo_frame(
    photo_path: Path | None,
    config: Config,
    canvas_size: tuple[int, int] = (1200, 1600),
) -> Image.Image:
    """Render a photo onto the portrait frame canvas, or an upload prompt if empty."""
    width, height = canvas_size

    if photo_path is None or not photo_path.exists():
        return _render_empty_gallery(config, canvas_size)

    with Image.open(photo_path) as raw:
        img = ImageOps.exif_transpose(raw).convert("RGB")

    img = _enhance_photo(img, config)

    mat = max(0, config.photo_mat_border)
    inner_w = max(100, width - 2 * mat)
    inner_h = max(100, height - 2 * mat)

    if config.photo_fit_mode == "contain":
        canvas = Image.new("RGB", (width, height), BG_WHITE)
        fitted = ImageOps.contain(img, (inner_w, inner_h), method=Image.LANCZOS)
        paste_x = (width - fitted.width) // 2
        paste_y = (height - fitted.height) // 2
        canvas.paste(fitted, (paste_x, paste_y))
        return canvas

    if config.photo_fit_mode == "cover":
        fitted = ImageOps.fit(img, (inner_w, inner_h), method=Image.LANCZOS, centering=(0.5, 0.5))
    else:
        # Default ("resize"): resize full image directly to portrait display size (1200x1600),
        # matching spectra6/image.py behavior without cropping.
        fitted = img.resize((inner_w, inner_h), Image.LANCZOS)

    if mat > 0:
        canvas = Image.new("RGB", (width, height), BG_WHITE)
        canvas.paste(fitted, (mat, mat))
        return canvas
    return fitted


def _render_empty_gallery(config: Config, canvas_size: tuple[int, int]) -> Image.Image:
    """Render a clean museum-styled prompt telling the user where to upload photos."""
    width, height = canvas_size
    canvas = Image.new("RGB", (width, height), BG_WHITE)
    draw = ImageDraw.Draw(canvas)

    sy = height / 1600.0
    title_font = _load_font(int(72 * sy), config, bold=True)
    body_font = _load_font(int(44 * sy), config, bold=False)
    url_font = _load_font(int(48 * sy), config, bold=True)

    ip = _get_local_ip()
    url = f"http://{ip}:{config.portal_port}"

    draw.text((width // 2, int(680 * sy)), "No Photos Yet", font=title_font, fill=INK_DARK, anchor="mm")
    draw.text(
        (width // 2, int(785 * sy)),
        "Upload photos from your local portal:",
        font=body_font,
        fill=INK_MUTED,
        anchor="mm",
    )
    draw.text((width // 2, int(875 * sy)), url, font=url_font, fill=INK_DARK, anchor="mm")
    return canvas
