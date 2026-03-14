# Chaewon Jeopardy

A custom Jeopardy game built with Python and PyQt6.

---

## Requirements

- Python 3.13+
- `ffmpeg.exe` in the project root (not included in repo — see below)

---

## Setup

**1. Clone the repo**
```
git clone <repo-url>
cd Chaewon_Jeproady
```

**2. Create and activate a virtual environment**
```
python -m venv .venv
.venv\Scripts\activate
```

**3. Install dependencies**
```
pip install -r requirements.txt
```

**4. Download ffmpeg**

ffmpeg is required for MP3 audio mixing but is not included in the repo (too large).

- Download the static build from: https://www.gyan.dev/ffmpeg/builds/
- Grab `ffmpeg-release-essentials.zip`, extract it, and copy `ffmpeg.exe` into the project root (alongside `main.py`)

---

## Running in dev mode

```
py main.py
```

Board files (`.json`) and assets are saved to the project root in dev mode.

---

## Building a distributable

```
build.bat
```

This will:
- Install/upgrade all dependencies
- Clean previous `build/` and `dist/` directories
- Run PyInstaller and output to `dist\Chaewon Jeopardy\`

To distribute, zip the `dist\Chaewon Jeopardy\` folder and share it. Recipients don't need Python or ffmpeg installed.

---

## Project structure

| File | Purpose |
|------|---------|
| `main.py` | Entry point, app setup |
| `board.py` | Data model (Board, Cell, Slide, SlideAsset) |
| `play_mode.py` | Gameplay UI |
| `edit_mode.py` | Board editor UI |
| `slide_widgets.py` | Shared slide rendering and editing widgets |
| `media_widget.py` | Video/audio playback widget |
| `audio_utils.py` | Audio mixing via pydub/ffmpeg |
| `players.py` | Player and score management |
| `build.bat` | PyInstaller build script |
