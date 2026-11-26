#!/usr/bin/env bash
# Download classic museum/gallery serif font (Playfair Display) for Raspberry Pi.
set -e

FONTS_DIR="$(dirname "$0")/assets/fonts"
mkdir -p "$FONTS_DIR"

echo "Downloading Playfair Display serif fonts..."
BASE_URL="https://github.com/google/fonts/raw/main/ofl/playfairdisplay/static"

for VARIANT in Regular Bold; do
    FILE="PlayfairDisplay-${VARIANT}.ttf"
    DEST="$FONTS_DIR/$FILE"
    if [ -f "$DEST" ]; then
        echo "  $FILE already exists, skipping"
    else
        curl -fsSL "$BASE_URL/$FILE" -o "$DEST" && echo "  Downloaded $FILE" || echo "  Failed to download $FILE (will fall back to system serif)"
    fi
done

ls -lh "$FONTS_DIR"
