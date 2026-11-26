# The Frame V2

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Platform: Raspberry Pi](https://img.shields.io/badge/Platform-Raspberry%20Pi-C51A4A)
![Display: Inky Impression 13.3" Spectra 6](https://img.shields.io/badge/Display-Inky%2013.3%22%20Spectra%206-2ea44f)
![Weather: Open-Meteo](https://img.shields.io/badge/Weather-Open--Meteo%20(No%20API%20Key)-orange)

A portrait-oriented smart E-Ink wall frame built for the **Pimoroni Inky Impression 13.3" (1600 × 1200, Spectra 6)** and **Raspberry Pi**.

---

## Features

- **Stage 1 — Morning Weather (`7:00 AM – 10:00 AM`):** Museum-styled portrait weather screen with high-contrast watercolor condition illustrations (`conditions/`), large serif temperature readout, chance of rain, and daily High/Low powered by [Open-Meteo](https://open-meteo.com/) (no API key required).
- **Stage 2 — Dynamic Daily Photo Frame (`10:00 AM – 7:00 AM`):** Automatically switches to your personal photo collection and randomly rotates to a new photo each day without repeating until the full gallery has been shown.
- **Passcode-Protected Local Web Portal:** Built-in web UI (`http://<pi-ip>:8080`, powered by Python's standard library) to upload, preview, and remove photos, show a specific photo or rotate immediately, trigger instant display refreshes, and edit `.env` settings live from any phone or browser on your Wi-Fi.
- **Auto-Start on Boot:** Includes `install_autostart.sh` to run `the-frame` automatically as a `systemd` service on every Raspberry Pi reboot.
- **Hardware-Free Mock Mode:** Render portrait `1200 × 1600` previews to `cache/preview.png` on macOS or Linux without an attached E-Ink panel.

---

## How It Works

```text
07:00 ──────────────────────── 10:00 ──────────────────────── 07:00
  │   Stage 1: Morning Weather   │   Stage 2: Photo Frame       │
  │   • Open-Meteo forecast      │   • 1 random photo / day     │
  │   • Watercolor illustration  │   • Non-repeating shuffle    │
  │   • Refreshes every 30 min   │   • Museum mat / cover / fit │
  └──────────────────────────────┴──────────────────────────────┘
                 ▲
                 │  Anytime via http://<pi-ip>:8080
                 └── Upload / delete / show photo / edit .env / refresh
```

---

## Hardware & System Requirements

- **Display:** Pimoroni Inky Impression 13.3" (Spectra 6, 1600 × 1200)
- **Host:** Raspberry Pi with SPI enabled (`sudo raspi-config` → Interface Options → SPI)
- **Software:** Python 3.9+ and Pimoroni's `inky` library installed in `~/.virtualenvs/pimoroni`

---

## Quick Start (Raspberry Pi)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/mrssd/The_Frame.git
   cd The_Frame
   ```

2. **Install Python dependencies** inside your Pimoroni virtualenv:
   ```bash
   ~/.virtualenvs/pimoroni/bin/pip install -r requirements.txt
   ```

3. **Download the serif display font** (Playfair Display):
   ```bash
   chmod +x setup_fonts.sh install_autostart.sh
   ./setup_fonts.sh
   ```

4. **Configure your environment:**
   ```bash
   cp .env.example .env
   nano .env
   ```
   Set your `LOCATION_NAME`, `LATITUDE`, `LONGITUDE`, `TIMEZONE`, and change `PORTAL_PASSCODE` from the default `1234`.

5. **Test a render** (use `--mock` to preview locally in `cache/preview.png` first):
   ```bash
   ~/.virtualenvs/pimoroni/bin/python main.py --mock --stage weather --once
   ~/.virtualenvs/pimoroni/bin/python main.py --stage weather --force --once
   ```

6. **Enable auto-start on boot:**
   ```bash
   ./install_autostart.sh
   ```

---

## CLI Usage

```bash
python main.py                                # Run scheduler + local web portal
python main.py --once                         # Run one stage cycle and exit
python main.py --stage weather --force --once # Force-render Stage 1 (Morning Weather)
python main.py --stage photo --force --once   # Force-render Stage 2 (Photo Frame)
python main.py --mock --once                  # Render preview PNG to cache/preview.png
python main.py --env /path/to/.env            # Use a custom .env file
```

---

## Web Portal

When `PORTAL_ENABLED=true` (the default), The Frame V2 serves a mobile-friendly web UI at `http://<pi-ip>:8080`.

- **Gallery Management:** Upload new photos, preview your collection, remove photos, jump to a specific photo, or trigger a random rotation.
- **Display Control:** Force an immediate display refresh from your phone.
- **Live Settings:** Edit `.env` values (location, schedule hours, photo fit mode, E-Ink color tuning, passcode) and apply them immediately without restarting or SSHing into the Pi.

---

## Configuration (`.env`)

Copy `.env.example` to `.env` to customize:

| Section | Key Variables | Description |
| --- | --- | --- |
| **Location & Weather** | `LOCATION_NAME`, `LATITUDE`, `LONGITUDE`, `TIMEZONE`, `TEMP_UNIT` | Coordinates and units (`C` or `F`) for Open-Meteo |
| **Schedule** | `MORNING_START_HOUR`, `MORNING_END_HOUR`, `REFRESH_INTERVAL_MINUTES`, `CHECK_INTERVAL_SECONDS` | Morning weather window (default `7`–`10`) and refresh cadence |
| **Display** | `DISPLAY_ORIENTATION`, `DISPLAY_ROTATION`, `DISPLAY_WIDTH`, `DISPLAY_HEIGHT`, `DISPLAY_SATURATION` | Portrait `1200 × 1600` canvas and Spectra 6 saturation |
| **Watercolor Tuning** | `SKETCH_CONTRAST`, `SKETCH_COLOR_BOOST`, `SKETCH_SHARPNESS`, `SKETCH_GAMMA` | E-Ink contrast/color boost for weather illustrations |
| **Photo Frame** | `PHOTO_FIT_MODE` (`resize`, `cover`, `contain`), `PHOTO_MAT_BORDER`, `PHOTO_CONTRAST`, `PHOTO_COLOR_BOOST`, `PHOTO_SHARPNESS` | Photo framing and E-Ink enhancement |
| **Web Portal** | `PORTAL_ENABLED`, `PORTAL_HOST`, `PORTAL_PORT`, `PORTAL_PASSCODE` | Local web UI (`0.0.0.0:8080`, default passcode `1234`) |
| **Mock Mode** | `MOCK_MODE`, `MOCK_OUTPUT_PATH` | Render to a local PNG instead of physical hardware |

---

## Service Management

Once `install_autostart.sh` has been run, manage the `systemd` service with:

```bash
sudo systemctl status the-frame       # Check service status
journalctl -u the-frame -f            # Stream live logs
sudo systemctl restart the-frame      # Restart (e.g. after git pull)
sudo systemctl stop the-frame         # Stop the service
```

---

## Troubleshooting

- **Pimoroni virtualenv not found during `install_autostart.sh`:** Pass your Python path explicitly:
  ```bash
  VENV_PYTHON=/path/to/python ./install_autostart.sh
  ```
- **Missing fonts:** If `setup_fonts.sh` cannot reach GitHub, the renderer falls back to system serif fonts, or you can set `FONT_BOLD_PATH` and `FONT_REGULAR_PATH` in `.env`.
- **Developing off-device:** Run `python main.py --mock --once` to inspect the rendered `1200 × 1600` output at `cache/preview.png` without an Inky display attached.

---

## Project Structure

```text
The_Frame/
├── main.py                  # Scheduler, CLI entry point, and stage controller
├── config.py                # .env configuration loader and live reloader
├── display.py               # Pimoroni Inky Impression 13.3" / mock PNG output
├── weather.py               # Open-Meteo API client and condition mapping
├── photos.py                # Non-repeating daily photo rotation library
├── portal.py                # Passcode-protected local web portal (port 8080)
├── stages/
│   ├── morning_weather.py   # Stage 1 portrait weather renderer
│   └── photo_frame.py       # Stage 2 photo frame renderer
├── conditions/              # Watercolor weather illustrations
├── setup_fonts.sh           # Downloads Playfair Display serif fonts
├── install_autostart.sh     # Installs and enables the-frame systemd service
├── requirements.txt         # Python dependencies (pillow, requests, python-dotenv)
├── .env.example             # Configuration template
└── LICENSE                  # MIT License
```

---

## License

This project is licensed under the [MIT License](LICENSE).
