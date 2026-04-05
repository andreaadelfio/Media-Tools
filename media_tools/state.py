from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SessionState:
    root_dir: Path | None = None
    recent_results: list[dict] = field(default_factory=list)


SESSION = SessionState()
