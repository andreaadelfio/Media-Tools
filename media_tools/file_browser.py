from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import librosa
from PIL import Image

from .config import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    THUMBNAIL_CACHE_DIR,
    THUMBNAIL_INDEX_FILE,
    VIDEO_EXTENSIONS,
)
from .utils import relative_to_root

IGNORED_DIR_NAMES = {
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "media_suite_output",
    "workspace",
}

_THUMBNAIL_INDEX_CACHE: dict | None = None


def classify_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    return "other"


def _should_skip_dir(path: Path) -> bool:
    return any(part.startswith(".") or part in IGNORED_DIR_NAMES for part in path.parts)


def scan_root(root_dir: Path, media_only: bool = True) -> list[dict]:
    items: list[dict] = []
    for path in sorted(root_dir.rglob("*")):
        if _should_skip_dir(path.relative_to(root_dir)):
            continue
        if not path.is_file():
            continue
        media_type = classify_path(path)
        if media_only and media_type == "other":
            continue
        items.append(
            {
                "name": path.name,
                "relative_path": relative_to_root(root_dir, path),
                "type": media_type,
                "size": path.stat().st_size,
            }
        )
    return items


def media_info(path: Path) -> dict:
    media_type = classify_path(path)
    info = {"type": media_type, "path": str(path)}
    if media_type == "image":
        image = cv2.imread(str(path))
        if image is not None:
            info["width"] = int(image.shape[1])
            info["height"] = int(image.shape[0])
    elif media_type == "video":
        cap = cv2.VideoCapture(str(path))
        if cap.isOpened():
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            info["fps"] = fps
            info["frames"] = frames
            info["duration"] = frames / fps if fps > 0 else 0.0
            info["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            info["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        cap.release()
    elif media_type == "audio":
        samples, sample_rate = librosa.load(str(path), sr=None, mono=True, duration=1)
        info["sample_rate"] = int(sample_rate)
        info["preview_seconds"] = float(len(samples) / sample_rate) if sample_rate else 0.0
    return info


def image_thumbnail_path(path: Path, size: int = 72) -> Path | None:
    cached = cached_thumbnail_path(path)
    if cached:
        return cached
    with Image.open(path) as image:
        preview = image.convert("RGB")
        preview.thumbnail((size, size))
        canvas = Image.new("RGB", (size, size), (244, 239, 230))
        offset = ((size - preview.width) // 2, (size - preview.height) // 2)
        canvas.paste(preview, offset)
        return store_thumbnail(path, canvas)


def video_thumbnail_path(path: Path, size: int = 72) -> Path | None:
    cached = cached_thumbnail_path(path)
    if cached:
        return cached
    cap = cv2.VideoCapture(str(path))
    success, frame = cap.read()
    cap.release()
    if not success or frame is None:
        return None
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(frame_rgb)
    image.thumbnail((size, size))
    canvas = Image.new("RGB", (size, size), (244, 239, 230))
    offset = ((size - image.width) // 2, (size - image.height) // 2)
    canvas.paste(image, offset)
    return store_thumbnail(path, canvas)


def load_thumbnail_index() -> dict:
    global _THUMBNAIL_INDEX_CACHE
    if _THUMBNAIL_INDEX_CACHE is not None:
        return _THUMBNAIL_INDEX_CACHE
    if not THUMBNAIL_INDEX_FILE.exists():
        _THUMBNAIL_INDEX_CACHE = {}
        return _THUMBNAIL_INDEX_CACHE
    try:
        _THUMBNAIL_INDEX_CACHE = json.loads(THUMBNAIL_INDEX_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _THUMBNAIL_INDEX_CACHE = {}
    return _THUMBNAIL_INDEX_CACHE


def save_thumbnail_index(index: dict) -> None:
    global _THUMBNAIL_INDEX_CACHE
    THUMBNAIL_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    _THUMBNAIL_INDEX_CACHE = index
    THUMBNAIL_INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")


def thumbnail_signature(path: Path) -> dict:
    stat = path.stat()
    return {
        "source": str(path.resolve()),
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }


def thumbnail_key(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()


def cached_thumbnail_path(path: Path) -> Path | None:
    index = load_thumbnail_index()
    key = thumbnail_key(path)
    entry = index.get(key)
    if not entry:
        return None
    signature = thumbnail_signature(path)
    if (
        entry.get("source") != signature["source"]
        or entry.get("mtime_ns") != signature["mtime_ns"]
        or entry.get("size") != signature["size"]
    ):
        return None
    thumb_path = Path(entry.get("thumbnail_path", ""))
    if not thumb_path.exists():
        return None
    return thumb_path


def store_thumbnail(path: Path, image: Image.Image) -> Path:
    THUMBNAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = thumbnail_key(path)
    thumb_path = THUMBNAIL_CACHE_DIR / f"{key}.jpg"
    image.save(thumb_path, format="JPEG", quality=85)

    index = load_thumbnail_index()
    signature = thumbnail_signature(path)
    index[key] = {
        **signature,
        "thumbnail_path": str(thumb_path.resolve()),
    }
    save_thumbnail_index(index)
    return thumb_path
