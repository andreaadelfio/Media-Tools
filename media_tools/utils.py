from __future__ import annotations

import base64
from pathlib import Path

from .config import DEFAULT_OUTPUT_DIRNAME


def clean_path_string(raw: str) -> str:
    return raw.strip().strip("\"'")


def ensure_within_root(root_dir: Path, target: Path) -> Path:
    resolved_root = root_dir.resolve()
    resolved_target = target.resolve()
    try:
        resolved_target.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Path outside selected root: {target}") from exc
    return resolved_target


def resolve_user_path(root_dir: Path, raw_path: str | Path) -> Path:
    candidate = Path(clean_path_string(str(raw_path))).expanduser()
    if not candidate.is_absolute():
        candidate = root_dir / candidate
    return ensure_within_root(root_dir, candidate)


def relative_to_root(root_dir: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root_dir.resolve()))


def root_output_dir(root_dir: Path) -> Path:
    path = root_dir / DEFAULT_OUTPUT_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_to_data_url(path: Path, mime_type: str) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
