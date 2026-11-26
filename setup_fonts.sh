#!/usr/bin/env bash
# Download classic museum/gallery serif font (Playfair Display) for Raspberry Pi.
set -euo pipefail

FONTS_DIR="$(dirname "$0")/assets/fonts"
mkdir -p "$FONTS_DIR"

echo "Downloading Playfair Display serif fonts..."

download_weight() {
    local WEIGHT="$1"
    local FILE="$2"
    local DEST="$FONTS_DIR/$FILE"

    if [ -f "$DEST" ]; then
        echo "  $FILE already exists, skipping"
        return
    fi

    local URL
    URL="$(curl -fsSL "https://fonts.googleapis.com/css?family=Playfair+Display:${WEIGHT}" \
        | sed -n 's/.*url(\(https:\/\/[^)]*\.ttf\)).*/\1/p' | head -n 1 || true)"

    if [ -n "$URL" ] && curl -fsSL "$URL" -o "$DEST"; then
        echo "  Downloaded $FILE"
    else
        rm -f "$DEST"
        echo "  Failed to download $FILE (will fall back to system serif)"
    fi
}

download_weight 400 "PlayfairDisplay-Regular.ttf"
download_weight 700 "PlayfairDisplay-Bold.ttf"

ls -lh "$FONTS_DIR"
