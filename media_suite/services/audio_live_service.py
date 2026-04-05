from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..config import PROJECT_ROOT


BIRD_AUDIO_CLI = PROJECT_ROOT.parent / "Bird Audio Suite" / "bird_audio_cli.py"


@dataclass
class LiveProcessState:
    process: subprocess.Popen | None = None
    log_path: Path | None = None
    detections_dir: Path | None = None
    started_at: str | None = None
    command_line: str | None = None
    log_handle: object | None = None


LIVE_PROCESS = LiveProcessState()


def build_live_command(
    detections_dir: Path,
    backend: str,
    device_index: int,
    min_confidence: float,
    frame_length: int,
    slice_interval: int,
    disable_denoise: bool,
    verbose: bool,
) -> list[str]:
    command = [
        sys.executable,
        str(BIRD_AUDIO_CLI),
        "live",
        "--backend",
        backend,
        "--device-index",
        str(device_index),
        "--min-confidence",
        str(min_confidence),
        "--frame-length",
        str(frame_length),
        "--slice-interval",
        str(slice_interval),
        "--detections-dir",
        str(detections_dir),
    ]
    if disable_denoise:
        command.append("--disable-denoise")
    if verbose:
        command.append("--verbose")
    return command


def live_status() -> dict:
    running = LIVE_PROCESS.process is not None and LIVE_PROCESS.process.poll() is None
    return {
        "running": running,
        "pid": LIVE_PROCESS.process.pid if running and LIVE_PROCESS.process else None,
        "started_at": LIVE_PROCESS.started_at,
        "log_path": str(LIVE_PROCESS.log_path) if LIVE_PROCESS.log_path else None,
        "detections_dir": str(LIVE_PROCESS.detections_dir) if LIVE_PROCESS.detections_dir else None,
        "command_line": LIVE_PROCESS.command_line,
    }


def start_live_process(
    detections_dir: Path,
    backend: str,
    device_index: int,
    min_confidence: float,
    frame_length: int,
    slice_interval: int,
    disable_denoise: bool,
    verbose: bool,
) -> dict:
    status = live_status()
    if status["running"]:
        return {"message": "Bird Audio Live e' gia attivo.", **status}

    if not BIRD_AUDIO_CLI.exists():
        raise FileNotFoundError(f"Bird Audio Suite non trovato: {BIRD_AUDIO_CLI}")

    detections_dir.mkdir(parents=True, exist_ok=True)
    log_path = detections_dir / "bird_audio_live.log"
    command = build_live_command(
        detections_dir=detections_dir,
        backend=backend,
        device_index=device_index,
        min_confidence=min_confidence,
        frame_length=frame_length,
        slice_interval=slice_interval,
        disable_denoise=disable_denoise,
        verbose=verbose,
    )

    log_handle = log_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        command,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        cwd=str(BIRD_AUDIO_CLI.parent.parent),
    )
    LIVE_PROCESS.process = process
    LIVE_PROCESS.log_path = log_path
    LIVE_PROCESS.detections_dir = detections_dir
    LIVE_PROCESS.started_at = datetime.now().isoformat(timespec="seconds")
    LIVE_PROCESS.command_line = subprocess.list2cmdline(command)
    LIVE_PROCESS.log_handle = log_handle
    return {"message": "Bird Audio Live avviato.", **live_status()}


def stop_live_process() -> dict:
    status = live_status()
    if not status["running"] or LIVE_PROCESS.process is None:
        return {"message": "Bird Audio Live non e' attivo.", **status}

    LIVE_PROCESS.process.terminate()
    try:
        LIVE_PROCESS.process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        LIVE_PROCESS.process.kill()
        LIVE_PROCESS.process.wait(timeout=5)

    if LIVE_PROCESS.log_handle is not None:
        try:
            LIVE_PROCESS.log_handle.close()
        except Exception:
            pass
        LIVE_PROCESS.log_handle = None

    status = live_status()
    LIVE_PROCESS.process = None
    return {"message": "Bird Audio Live fermato.", **status}
