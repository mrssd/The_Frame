"""
Stage 1 — Morning Weather Conditions Renderer (Portrait 1200 x 1600).

Museum-frame aesthetic:
  - Upper section (0..1020 px): large, auto-cropped, E-Ink-enhanced watercolor
    weather sketch floating on pure white.
  - Lower section (1020..1600 px): two-column museum plaque layout:
      * Left column: huge bold temperature degree + condition label.
      * Right column: Chance of Rain (droplet + %) stacked above bold High / Low.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

from config import BASE_DIR, Config
from weather import WeatherSnapshot

logger = logging.getLogger(__name__)

# Clean Spectra-6 friendly gallery palette
BG_WHITE = (255, 255, 255)
INK_BLACK = (15, 15, 15)
INK_DARK = (38, 38, 38)
INK_MUTED = (88, 88, 88)
DIVIDER_COLOR = (195, 195, 195)
RAIN_BLUE = (20, 86, 174)


def _find_font(preferred_path: str, bold: bool) -> tuple[str, int] | None:
    """
    Return (font_path, font_index) prioritizing classic museum/editorial serif fonts
    across local assets, Raspberry Pi OS, and macOS.
    """
    candidates: list[tuple[Path, int]] = []
    if preferred_path:
        candidates.append((Path(preferred_path), 0))

    if bold:
        candidates.extend([
            (BASE_DIR / "assets/fonts/PlayfairDisplay-Bold.ttf", 0),
            (BASE_DIR / "assets/fonts/CormorantGaramond-Bold.ttf", 0),
            (Path("/System/Library/Fonts/Supplemental/Baskerville.ttc"), 4),
            (Path("/System/Library/Fonts/Supplemental/Didot.ttc"), 2),
            (Path("/System/Library/Fonts/Supplemental/Georgia Bold.ttf"), 0),
            (Path("/System/Library/Fonts/Supplemental/Bodoni 72.ttc"), 2),
            (Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"), 0),
            (Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"), 0),
            (Path("/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf"), 0),
        ])
    else:
        candidates.extend([
            (BASE_DIR / "assets/fonts/PlayfairDisplay-Regular.ttf", 0),
            (BASE_DIR / "assets/fonts/CormorantGaramond-Regular.ttf", 0),
            (Path("/System/Library/Fonts/Supplemental/Baskerville.ttc"), 0),
            (Path("/System/Library/Fonts/Supplemental/Didot.ttc"), 0),
            (Path("/System/Library/Fonts/Supplemental/Georgia.ttf"), 0),
            (Path("/System/Library/Fonts/Supplemental/Bodoni 72.ttc"), 0),
            (Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"), 0),
            (Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"), 0),
            (Path("/usr/share/fonts/truetype/freefont/FreeSerif.ttf"), 0),
        ])

    for path, idx in candidates:
        if path.exists():
            return (str(path), idx)
    return None


def _load_font(size: int, config: Config, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    preferred = config.font_bold_path if bold else config.font_regular_path
    found = _find_font(preferred, bold=bold)
    if found:
        font_path, idx = found
        try:
            return ImageFont.truetype(font_path, size=size, index=idx)
        except Exception:
            try:
                return ImageFont.truetype(font_path, size=size, index=0)
            except Exception as exc:
                logger.warning("Could not load font %s: %s", font_path, exc)
    return ImageFont.load_default()


def _draw_raindrop(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple[int, int, int]) -> None:
    """Draw a crisp minimalist raindrop centered around (cx, cy)."""
    r = size * 0.34
    tip_y = cy - size * 0.52
    circle_cy = cy + size * 0.16

    left_x = cx - r * 0.96
    right_x = cx + r * 0.96
    join_y = circle_cy - r * 0.25

    draw.polygon([(cx, tip_y), (right_x, join_y), (left_x, join_y)], fill=color)
    draw.ellipse(
        [cx - r, circle_cy - r, cx + r, circle_cy + r],
        fill=color,
    )


def _trim_white_margin(img: Image.Image, white_thresh: int = 242, pad: int = 16) -> Image.Image:
    """Crop excess blank paper margin around the watercolor illustration so it fills the frame."""
    gray = img.convert("L")
    # Mask of non-white painted pixels
    mask = gray.point(lambda p: 255 if p < white_thresh else 0)
    bbox = mask.getbbox()
    if not bbox:
        return img
    left = max(0, bbox[0] - pad)
    top = max(0, bbox[1] - pad)
    right = min(img.width, bbox[2] + pad)
    bottom = min(img.height, bbox[3] + pad)
    return img.crop((left, top, right, bottom))


def _enhance_sketch(img: Image.Image, config: Config) -> Image.Image:
    """
    Deepen pale watercolor pigments so soft clouds stay rich and clearly visible
    on 6-color E-Ink Spectra 6 displays while preserving a spotless white background.
    """
    # 1. Clean faint off-white paper grain to pure white before deepening pigments
    bg_cutoff = 243
    r, g, b = img.split()
    gray = img.convert("L")
    # Build a mask of painted pixels (anything darker than bg_cutoff)
    painted_mask = gray.point(lambda p: 255 if p < bg_cutoff else 0)

    # 2. Apply gamma deepening (gamma > 1 darkens pale pastel midtones/highlights!)
    gamma = max(0.5, config.sketch_gamma)
    gamma_lut = [int(round(((i / 255.0) ** gamma) * 255.0)) for i in range(256)]
    deepened = img.point(gamma_lut * 3)

    # 3. Boost color richness, contrast, and crispness
    if config.sketch_color_boost != 1.0:
        deepened = ImageEnhance.Color(deepened).enhance(config.sketch_color_boost)
    if config.sketch_contrast != 1.0:
        deepened = ImageEnhance.Contrast(deepened).enhance(config.sketch_contrast)
    if config.sketch_sharpness != 1.0:
        deepened = ImageEnhance.Sharpness(deepened).enhance(config.sketch_sharpness)

    # 4. Composite deepened pigments onto pure white so background has zero box artifacts
    pure_white = Image.new("RGB", img.size, BG_WHITE)
    return Image.composite(deepened, pure_white, painted_mask)


def _load_condition_sketch(config: Config, filename: str, max_w: int, max_h: int) -> Image.Image | None:
    """Load, trim whitespace, enhance for E-Ink, and scale up cleanly to fit (max_w, max_h)."""
    path = config.conditions_dir / filename
    if not path.exists():
        logger.warning("Condition image not found: %s", path)
        fallback = config.conditions_dir / "cloudyJPG.JPG"
        if not fallback.exists():
            return None
        path = fallback

    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    img = _trim_white_margin(img)
    img = _enhance_sketch(img, config)

    # Scale proportionally (allowing upscale for smaller cropped clouds so they fill the hero area)
    scale = min(max_w / img.width, max_h / img.height)
    new_w = max(1, int(round(img.width * scale)))
    new_h = max(1, int(round(img.height * scale)))
    img = img.resize((new_w, new_h), Image.LANCZOS)
    return img


def render_morning_weather(
    weather: WeatherSnapshot,
    config: Config,
    now: datetime,
    canvas_size: tuple[int, int] = (1200, 1600),
) -> Image.Image:
    """Render the Stage 1 portrait morning weather display."""
    width, height = canvas_size
    canvas = Image.new("RGB", (width, height), BG_WHITE)
    draw = ImageDraw.Draw(canvas)

    sx = width / 1200.0
    sy = height / 1600.0

    # ── 1. Upper Hero Section (y=40..1000): Large, vivid watercolor sketch ────
    sketch_box_w = int(1040 * sx)
    sketch_box_h = int(920 * sy)
    sketch = _load_condition_sketch(config, weather.image_filename, sketch_box_w, sketch_box_h)
    if sketch is not None:
        paste_x = (width - sketch.width) // 2
        paste_y = int(50 * sy) + (sketch_box_h - sketch.height) // 2
        canvas.paste(sketch, (paste_x, paste_y))

    # ── 2. Left Column: Big Temperature Degree + Condition Label ──────────────
    left_cx = int(350 * sx)

    temp_font = _load_font(int(310 * sy), config, bold=True)
    num_text = str(round(weather.temperature))
    deg_text = "°"
    deg_bbox = draw.textbbox((0, 0), deg_text, font=temp_font)
    deg_w = deg_bbox[2] - deg_bbox[0]

    draw.text(
        (left_cx + int(deg_w * 0.22), int(1245 * sy)),
        f"{num_text}{deg_text}",
        font=temp_font,
        fill=INK_BLACK,
        anchor="mm",
    )

    cond_font = _load_font(int(54 * sy), config, bold=False)
    draw.text(
        (left_cx, int(1468 * sy)),
        weather.condition,
        font=cond_font,
        fill=INK_DARK,
        anchor="mm",
    )

    # ── 3. Right Column: Chance of Rain + Bold High / Low ─────────────────────
    right_cx = int(910 * sx)

    rain_pct_font = _load_font(int(104 * sy), config, bold=True)
    rain_lbl_font = _load_font(int(42 * sy), config, bold=False)

    rain_color = RAIN_BLUE if weather.rain_chance >= 20 else INK_DARK
    pct_text = f"{weather.rain_chance}%"
    lbl_text = "Chance of Rain"

    pct_bbox = draw.textbbox((0, 0), pct_text, font=rain_pct_font)
    pct_w = pct_bbox[2] - pct_bbox[0]
    drop_size = int(72 * sy)
    gap = int(22 * sx)

    total_row_w = drop_size + gap + pct_w
    row_start_x = right_cx - total_row_w // 2
    row_y = int(1185 * sy)

    _draw_raindrop(
        draw,
        cx=row_start_x + drop_size // 2,
        cy=row_y,
        size=drop_size,
        color=rain_color,
    )
    draw.text(
        (row_start_x + drop_size + gap, row_y),
        pct_text,
        font=rain_pct_font,
        fill=rain_color,
        anchor="lm",
    )

    draw.text(
        (right_cx, int(1275 * sy)),
        lbl_text,
        font=rain_lbl_font,
        fill=INK_MUTED,
        anchor="mm",
    )

    # Bold, clearly legible High / Low below Chance of Rain
    hl_font = _load_font(int(62 * sy), config, bold=True)
    draw.text(
        (right_cx, int(1435 * sy)),
        f"H {round(weather.today_high)}°   ·   L {round(weather.today_low)}°",
        font=hl_font,
        fill=INK_DARK,
        anchor="mm",
    )

    return canvas
