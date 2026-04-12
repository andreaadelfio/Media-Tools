from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "media_tools" / "static"
DEFAULT_OUTPUT_DIRNAME = "media_tools_output"
DEFAULT_SPECIES_FILE = PROJECT_ROOT / "species_names.txt"
GLOBAL_CACHE_DIR = Path.home() / ".media-tools"
THUMBNAIL_CACHE_DIR = GLOBAL_CACHE_DIR / "thumbnails"
THUMBNAIL_INDEX_FILE = GLOBAL_CACHE_DIR / "thumbnail_index.json"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}

THUMBNAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
