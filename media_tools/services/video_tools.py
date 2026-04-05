from __future__ import annotations

import base64
import subprocess
from pathlib import Path

import cv2
import imageio


def parse_roi(raw_roi: str | None) -> tuple[int, int, int, int] | None:
    if not raw_roi:
        return None
    parts = [segment.strip() for segment in raw_roi.split(",")]
    if len(parts) != 4:
        raise ValueError("ROI deve avere formato x,y,w,h")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def apply_roi_crop(frame, roi):
    if not roi:
        return frame
    x, y, w, h = roi
    x = max(0, min(x, frame.shape[1]))
    y = max(0, min(y, frame.shape[0]))
    w = min(w, frame.shape[1] - x)
    h = min(h, frame.shape[0] - y)
    return frame[y:y + h, x:x + w]


def video_info(video_path: Path) -> dict:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Video non leggibile: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    return {
        "fps": fps,
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "duration": frame_count / fps if fps > 0 else 0.0,
    }


def frame_preview(video_path: Path, time_seconds: float, max_width: int = 800) -> dict:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Video non leggibile: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_number = max(0, int(time_seconds * fps)) if fps > 0 else 0
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    success, frame = cap.read()
    cap.release()
    if not success or frame is None:
        raise ValueError("Frame non disponibile")

    height, width = frame.shape[:2]
    if width > max_width:
        scale = max_width / width
        frame = cv2.resize(frame, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_LINEAR)
    success, buffer = cv2.imencode(".jpg", frame)
    if not success:
        raise ValueError("Impossibile serializzare il frame")
    encoded = base64.b64encode(buffer).decode("ascii")
    return {"frame": f"data:image/jpeg;base64,{encoded}"}


def extract_frames(video_path: Path, output_dir: Path, start_time: float, end_time: float, roi=None) -> dict:
    info = video_info(video_path)
    cap = cv2.VideoCapture(str(video_path))
    fps = info["fps"]
    start_frame = max(0, int(start_time * fps))
    end_frame = max(start_frame, int(end_time * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    current = start_frame
    while current <= end_frame:
        success, frame = cap.read()
        if not success or frame is None:
            break
        cropped = apply_roi_crop(frame, roi)
        output_path = output_dir / f"{video_path.stem}_frame{current}.jpg"
        cv2.imwrite(str(output_path), cropped)
        written.append(str(output_path))
        current += 1
    cap.release()
    return {"output_dir": str(output_dir), "frames_written": len(written), "files": written}


def create_gif(video_path: Path, output_dir: Path, start_time: float, end_time: float, roi=None) -> dict:
    info = video_info(video_path)
    cap = cv2.VideoCapture(str(video_path))
    fps = info["fps"] or 10.0
    start_frame = max(0, int(start_time * fps))
    end_frame = max(start_frame, int(end_time * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frames = []

    current = start_frame
    while current <= end_frame:
        success, frame = cap.read()
        if not success or frame is None:
            break
        cropped = apply_roi_crop(frame, roi)
        frames.append(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB))
        current += 1
    cap.release()
    if not frames:
        raise ValueError("Nessun frame disponibile per la GIF")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_path.stem}_{start_frame}_{end_frame}.gif"
    imageio.mimsave(str(output_path), frames, fps=fps)
    return {"output": str(output_path), "frames": len(frames)}


def get_resolution_string(resolution_input: str | None) -> str | None:
    if not resolution_input:
        return None
    common = {
        "4k": "-1:2160",
        "2k": "-1:1440",
        "1080p": "-1:1080",
        "1080": "-1:1080",
        "720p": "-1:720",
        "720": "-1:720",
        "480p": "-1:480",
        "480": "-1:480",
        "360p": "-1:360",
        "360": "-1:360",
    }
    return common.get(resolution_input.lower(), resolution_input)


def convert_gopro(video_path: Path, output_dir: Path, resolution: str | None, codec: str, crf: int, preset: str) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = resolution.lower().replace(":", "x") if resolution else "converted"
    output_path = output_dir / f"{video_path.stem}_{suffix}{video_path.suffix}"
    command = ["ffmpeg", "-i", str(video_path), "-c:v", codec, "-crf", str(crf), "-preset", preset]
    scale_str = get_resolution_string(resolution)
    if scale_str:
        command += ["-vf", f"scale={scale_str}"]
    command += ["-y", str(output_path)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return {"output": str(output_path), "command": command}


def convert_for_web(video_path: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_path.stem}_web.mp4"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-vf",
        "scale=-1:720",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return {"output": str(output_path), "command": command}
