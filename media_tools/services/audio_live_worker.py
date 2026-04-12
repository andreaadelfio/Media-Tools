from __future__ import annotations

import argparse
import signal
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from .audio_tools import denoise_signal


SAMPLE_RATE = 48_000
STOP_REQUESTED = False


def log(message: str) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{timestamp}] {message}", flush=True)


def request_stop(signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True
    log(f"Segnale di stop ricevuto ({signum}).")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Worker live per Bird Audio.")
    parser.add_argument("live", nargs="?")
    parser.add_argument("--backend", default="sounddevice")
    parser.add_argument("--device-index", type=int, default=0)
    parser.add_argument("--min-confidence", type=float, default=0.1)
    parser.add_argument("--frame-length", type=int, default=512)
    parser.add_argument("--slice-interval", type=int, default=300)
    parser.add_argument("--detections-dir", type=Path, required=True)
    parser.add_argument("--disable-denoise", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def normalize_backend(name: str) -> str:
    backend = (name or "sounddevice").strip().lower()
    if backend in {"sounddevice", "auto"}:
        return "sounddevice"
    log(f"Backend `{backend}` non supportato internamente, uso `sounddevice`.")
    return "sounddevice"


def record_audio_slice(duration_seconds: float, device_index: int, frame_length: int) -> np.ndarray:
    chunk_seconds = max(frame_length / SAMPLE_RATE, 0.5)
    remaining = max(float(duration_seconds), chunk_seconds)
    chunks: list[np.ndarray] = []

    while remaining > 0 and not STOP_REQUESTED:
        current_seconds = min(remaining, chunk_seconds)
        frames = max(int(SAMPLE_RATE * current_seconds), 1)
        recorded = sd.rec(
            frames,
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=device_index,
            blocking=True,
        )
        chunks.append(np.asarray(recorded, dtype=np.float32).reshape(-1))
        remaining -= current_seconds

    if not chunks:
        return np.asarray([], dtype=np.float32)
    return np.concatenate(chunks)


def describe_detection(detection: dict) -> str:
    common_name = str(detection.get("common_name") or "").strip()
    scientific_name = str(detection.get("scientific_name") or "").strip()
    if common_name and scientific_name and common_name.lower() != scientific_name.lower():
        return f"{common_name} / {scientific_name}"
    return common_name or scientific_name or "Specie sconosciuta"


def analyze_slice(analyzer: object, audio_path: Path, min_confidence: float) -> list[dict]:
    from birdnetlib import Recording

    recording = Recording(analyzer, str(audio_path), min_conf=min_confidence, date=datetime.now())
    recording.analyze()
    return [
        detection
        for detection in recording.detections
        if float(detection.get("confidence", 0.0)) >= min_confidence
    ]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    backend = normalize_backend(args.backend)
    args.detections_dir.mkdir(parents=True, exist_ok=True)

    try:
        from birdnetlib.analyzer import Analyzer
    except ModuleNotFoundError as exc:
        log("BirdNET non disponibile. Installa tensorflow o tflite_runtime nel venv del progetto.")
        return 2

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    analyzer = Analyzer()
    log(
        "Bird Audio Live avviato "
        f"(backend={backend}, device_index={args.device_index}, min_confidence={args.min_confidence}, "
        f"slice_interval={args.slice_interval}s)."
    )

    while not STOP_REQUESTED:
        try:
            samples = record_audio_slice(args.slice_interval, args.device_index, args.frame_length)
            if STOP_REQUESTED:
                break
            if samples.size == 0:
                time.sleep(0.2)
                continue

            processed = samples
            if not args.disable_denoise:
                processed = denoise_signal(samples, SAMPLE_RATE)

            with tempfile.NamedTemporaryFile(
                suffix=".wav",
                prefix="bird_live_",
                dir=args.detections_dir,
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)

            try:
                sf.write(temp_path, processed, SAMPLE_RATE)
                detections = analyze_slice(analyzer, temp_path, args.min_confidence)
            finally:
                temp_path.unlink(missing_ok=True)

            if detections:
                log(f"{len(detections)} rilevamenti trovati nell'ultima finestra audio.")
                for detection in detections:
                    label = describe_detection(detection)
                    confidence = float(detection.get("confidence", 0.0))
                    log(f"rilevato: {label} (confidence: {confidence:.3f})")
            elif args.verbose:
                log("Nessun uccello rilevato nell'ultima finestra audio.")
        except Exception as exc:
            log(f"Errore Bird Audio Live: {exc}")
            time.sleep(1.0)

    log("Bird Audio Live terminato.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
