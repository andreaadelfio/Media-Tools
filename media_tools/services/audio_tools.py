from __future__ import annotations

from datetime import datetime
from pathlib import Path

import librosa
import numpy as np
import scipy.io.wavfile as wavfile
import wikipediaapi

from ..config import DEFAULT_SPECIES_FILE


def normalize_audio(samples: np.ndarray) -> np.ndarray:
    array = np.asarray(samples)
    if array.size == 0:
        return np.asarray([], dtype=np.float32)
    if np.issubdtype(array.dtype, np.integer):
        max_value = max(abs(np.iinfo(array.dtype).min), np.iinfo(array.dtype).max)
        return array.astype(np.float32) / float(max_value)
    return array.astype(np.float32)


def to_int16(samples: np.ndarray) -> np.ndarray:
    normalized = np.clip(normalize_audio(samples), -1.0, 1.0)
    return (normalized * 32767.0).astype(np.int16)


def write_wav_mono(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(path, sample_rate, to_int16(samples))


def load_audio(path: Path, sample_rate: int | None = None) -> tuple[np.ndarray, int]:
    samples, loaded_rate = librosa.load(str(path), sr=sample_rate, mono=True, res_type="kaiser_fast")
    return samples.astype(np.float32), int(loaded_rate)


def denoise_signal(
    samples: np.ndarray,
    sample_rate: int,
    high_pass_hz: float = 500.0,
    noise_reduction_factor: float = 2.0,
) -> np.ndarray:
    signal = normalize_audio(samples)
    if signal.size == 0:
        return signal
    signal_stft = librosa.stft(signal)
    noise_profile = np.mean(np.abs(signal_stft), axis=1, keepdims=True)
    signal_magnitude = np.abs(signal_stft)
    signal_phase = np.angle(signal_stft)
    filtered_magnitude = np.maximum(signal_magnitude - noise_reduction_factor * noise_profile, 0.0)
    freqs = librosa.fft_frequencies(sr=sample_rate)
    filtered_magnitude[freqs < high_pass_hz, :] = 0.0
    rebuilt = filtered_magnitude * np.exp(1j * signal_phase)
    return librosa.istft(rebuilt, length=len(signal)).astype(np.float32)


class SpeciesCatalog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_SPECIES_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.names: dict[str, tuple[str, str]] = {}
        self._wiki = wikipediaapi.Wikipedia(
            language="it",
            extract_format=wikipediaapi.ExtractFormat.HTML,
            user_agent="media-tools",
        )
        self.load()

    def load(self) -> None:
        self.names = {}
        if not self.path.exists():
            self.path.touch()
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                parts = line.split("|", 2)
                if len(parts) == 3:
                    self.names[parts[0]] = (parts[2], parts[1])

    def save(self) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            for scientific_name in sorted(self.names):
                italian_name, english_name = self.names[scientific_name]
                handle.write(f"{scientific_name}|{english_name}|{italian_name}\n")

    def lookup_italian_name(self, scientific_name: str) -> str | None:
        page = self._wiki.page(scientific_name)
        if not page.exists():
            return None
        summary = page.summary or ""
        if "<b>" in summary:
            try:
                return summary.split("<b>", 1)[1].split("<", 1)[0].title()
            except (IndexError, ValueError):
                return None
        return None

    def ensure_species(self, detections: list[dict]) -> None:
        changed = False
        for detection in detections:
            scientific_name = detection.get("scientific_name", "").strip()
            english_name = detection.get("common_name", "").strip()
            if not scientific_name:
                continue
            if scientific_name not in self.names:
                self.names[scientific_name] = (
                    self.lookup_italian_name(scientific_name) or english_name or scientific_name,
                    english_name,
                )
                changed = True
        if changed:
            self.save()

    def display_names(self, scientific_name: str, english_name: str) -> tuple[str, str]:
        italian_name, stored_english = self.names.get(scientific_name, (english_name or scientific_name, english_name))
        return italian_name or scientific_name, stored_english or english_name


def aggregate_detections_by_species(detections: list[dict], duration_seconds: float, min_confidence: float) -> dict:
    grouped = {}
    for detection in detections:
        confidence = float(detection.get("confidence", 0.0))
        if confidence < min_confidence:
            continue
        scientific_name = detection.get("scientific_name", "")
        english_name = detection.get("common_name", "")
        start_sec = max(float(detection.get("start_time", 0.0)), 0.0)
        end_sec = min(float(detection.get("end_time", 0.0)), float(duration_seconds))
        if end_sec <= start_sec:
            end_sec = min(start_sec + 1.0, float(duration_seconds) or start_sec + 1.0)
        previous = grouped.get(scientific_name)
        if previous is None:
            grouped[scientific_name] = (start_sec, end_sec, round(confidence, 3), english_name)
        else:
            grouped[scientific_name] = (
                min(start_sec, previous[0]),
                max(end_sec, previous[1]),
                max(round(confidence, 3), previous[2]),
                english_name or previous[3],
            )
    return grouped


def apply_clip_span_policy(grouped_detections: dict, duration_seconds: float, clip_span: str) -> dict:
    adjusted = {}
    for scientific_name, (start_sec, end_sec, confidence, english_name) in grouped_detections.items():
        next_start = max(0.0, start_sec)
        next_end = max(next_start, end_sec)
        if clip_span == "full_slice":
            next_start = 0.0
            next_end = duration_seconds
        elif clip_span == "from_detection":
            next_end = duration_seconds
        adjusted[scientific_name] = (next_start, next_end, confidence, english_name)
    return adjusted


def export_detection_clips(
    samples: np.ndarray,
    sample_rate: int,
    grouped_detections: dict,
    species_catalog: SpeciesCatalog,
    destination_dir: Path,
) -> list[str]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    exported = []
    normalized = normalize_audio(samples)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for scientific_name, (start_sec, end_sec, confidence, english_name) in grouped_detections.items():
        start_index = max(int(start_sec * sample_rate), 0)
        end_index = min(int(end_sec * sample_rate), len(normalized))
        if end_index <= start_index:
            continue
        italian_name, _ = species_catalog.display_names(scientific_name, english_name)
        output_path = destination_dir / f"{italian_name.replace('/', '_')}_{timestamp}_{confidence:.3f}.wav"
        write_wav_mono(output_path, normalized[start_index:end_index], sample_rate)
        exported.append(str(output_path))
    return exported


def run_birdnet_batch(
    files: list[Path],
    output_dir: Path,
    latitude: float,
    longitude: float,
    min_confidence: float,
    export_clips: bool,
    clip_span: str,
) -> dict:
    try:
        from birdnetlib import Recording
        from birdnetlib.analyzer import Analyzer
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "BirdNET richiede dipendenze ML aggiuntive. Installa tensorflow oppure tflite_runtime nel venv della suite."
        ) from exc

    analyzer = Analyzer()
    species_catalog = SpeciesCatalog()
    results = []

    for file_path in files:
        recording = Recording(
            analyzer,
            str(file_path),
            lat=latitude,
            lon=longitude,
            date=datetime.now(),
            min_conf=min_confidence,
        )
        recording.analyze()
        detections = recording.detections
        species_catalog.ensure_species(detections)
        samples, sample_rate = load_audio(file_path)
        duration_seconds = len(samples) / sample_rate if sample_rate else 0.0
        grouped = aggregate_detections_by_species(detections, duration_seconds, min_confidence)
        grouped = apply_clip_span_policy(grouped, duration_seconds, clip_span)
        exported = []
        if export_clips:
            exported = export_detection_clips(samples, sample_rate, grouped, species_catalog, output_dir / file_path.stem)
        species_rows = []
        for scientific_name, (start_sec, end_sec, confidence, english_name) in grouped.items():
            italian_name, english_resolved = species_catalog.display_names(scientific_name, english_name)
            species_rows.append(
                {
                    "scientific_name": scientific_name,
                    "english_name": english_resolved,
                    "italian_name": italian_name,
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                    "confidence": confidence,
                }
            )
        results.append({"input": str(file_path), "detections": species_rows, "exported_clips": exported})
    return {"results": results}


def run_birdnet_denoise(audio_path: Path, output_dir: Path, high_pass_hz: float, noise_reduction_factor: float) -> dict:
    samples, sample_rate = load_audio(audio_path)
    denoised = denoise_signal(samples, sample_rate, high_pass_hz=high_pass_hz, noise_reduction_factor=noise_reduction_factor)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{audio_path.stem}_denoised.wav"
    write_wav_mono(output_path, denoised, sample_rate)
    return {"input": str(audio_path), "output": str(output_path)}
