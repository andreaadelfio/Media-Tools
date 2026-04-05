from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .catalog import TOOLS
from .config import STATIC_DIR
from .file_browser import image_thumbnail_path, media_info, scan_root, video_thumbnail_path
from .services.audio_tools import run_birdnet_batch, run_birdnet_denoise
from .services.audio_live_service import live_status, start_live_process, stop_live_process
from .services.photo_tools import process_photo
from .services.stereo_tools import create_overlay, parse_point
from .services.video_tools import convert_for_web, convert_gopro, create_gif, extract_frames, frame_preview, parse_roi
from .state import SESSION
from .utils import resolve_user_path, root_output_dir


class RootPayload(BaseModel):
    root_path: str


class RunPayload(BaseModel):
    selected_files: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)


def pick_directory_dialog(initial_dir: Path | None = None) -> str | None:
    import subprocess

    start_dir = str((initial_dir or Path.home()).resolve())
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Seleziona la cartella root della sessione'
$dialog.ShowNewFolderButton = $false
$dialog.SelectedPath = '{start_dir.replace("'", "''")}'
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
  Write-Output $dialog.SelectedPath
}}
"""
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-STA",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.strip() or "Dialog cartelle non disponibile.")
    selected = result.stdout.strip()
    return selected or None


def create_app() -> FastAPI:
    app = FastAPI(title="Media Browser Suite")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/favicon.ico")
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/tools")
    def get_tools() -> list[dict]:
        return TOOLS

    @app.get("/api/session")
    def get_session() -> dict:
        return {
            "root_path": str(SESSION.root_dir) if SESSION.root_dir else None,
            "recent_results": SESSION.recent_results[-10:],
        }

    @app.post("/api/session/root")
    def set_root(payload: RootPayload) -> dict:
        root_dir = Path(payload.root_path).expanduser()
        if not root_dir.exists() or not root_dir.is_dir():
            raise HTTPException(status_code=400, detail="La cartella selezionata non esiste.")
        SESSION.root_dir = root_dir.resolve()
        return {"root_path": str(SESSION.root_dir)}

    @app.post("/api/session/pick-root")
    def pick_root() -> dict:
        selected = pick_directory_dialog(SESSION.root_dir)
        if not selected:
            raise HTTPException(status_code=400, detail="Selezione cartella annullata.")
        root_dir = Path(selected).expanduser().resolve()
        SESSION.root_dir = root_dir
        return {"root_path": str(root_dir)}

    @app.get("/api/files")
    def list_files() -> list[dict]:
        if SESSION.root_dir is None:
            raise HTTPException(status_code=400, detail="Imposta prima una cartella root.")
        return scan_root(SESSION.root_dir)

    @app.get("/api/media/thumbnail")
    def get_thumbnail(path: str) -> FileResponse:
        root_dir = _require_root()
        resolved = resolve_user_path(root_dir, path)
        media_type = media_info(resolved).get("type")
        if media_type == "image":
            thumbnail_path = image_thumbnail_path(resolved)
            if thumbnail_path is not None:
                return FileResponse(thumbnail_path, media_type="image/jpeg")
        if media_type == "video":
            thumbnail_path = video_thumbnail_path(resolved)
            if thumbnail_path is not None:
                return FileResponse(thumbnail_path, media_type="image/jpeg")
        raise HTTPException(status_code=404, detail="Thumbnail non disponibile.")

    @app.get("/api/media/info")
    def get_media_info(path: str) -> dict:
        root_dir = _require_root()
        resolved = resolve_user_path(root_dir, path)
        return media_info(resolved)

    @app.get("/api/media/frame")
    def get_video_frame(path: str, time_seconds: float = 0) -> dict:
        root_dir = _require_root()
        resolved = resolve_user_path(root_dir, path)
        return frame_preview(resolved, time_seconds)

    @app.get("/api/file")
    def serve_file(path: str) -> FileResponse:
        root_dir = _require_root()
        resolved = resolve_user_path(root_dir, path)
        if not resolved.is_file():
            raise HTTPException(status_code=400, detail="Il path richiesto non e' un file.")
        return FileResponse(resolved)

    @app.post("/api/run/{tool_id}")
    def run_tool(tool_id: str, payload: RunPayload) -> dict:
        root_dir = _require_root()
        try:
            result = dispatch_tool(root_dir, tool_id, payload)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        SESSION.recent_results.append({"tool_id": tool_id, "result": result})
        return result

    return app


def _require_root() -> Path:
    if SESSION.root_dir is None:
        raise HTTPException(status_code=400, detail="Imposta prima una cartella root.")
    return SESSION.root_dir


def dispatch_tool(root_dir: Path, tool_id: str, payload: RunPayload) -> dict:
    params = payload.params or {}
    selected = [resolve_user_path(root_dir, path) for path in payload.selected_files]
    suite_output = root_output_dir(root_dir)
    tool_output = suite_output / tool_id
    tool_output.mkdir(parents=True, exist_ok=True)

    if tool_id == "photo_naturalize":
        if not selected:
            raise ValueError("Seleziona almeno un'immagine.")
        return {
            "results": [
                process_photo(
                    source=path,
                    output_dir=tool_output / path.stem,
                    denoise=float(params.get("denoise", 1.4)),
                    sharpen=float(params.get("sharpen", 1.4)),
                    test_crops=bool(params.get("test_crops", False)),
                )
                for path in selected
            ]
        }

    if tool_id == "stereo_overlay":
        left_path = resolve_user_path(root_dir, params.get("left_path", ""))
        right_path = resolve_user_path(root_dir, params.get("right_path", ""))
        return create_overlay(
            left_path=left_path,
            right_path=right_path,
            left_point=parse_point(params.get("left_point", "")),
            right_point=parse_point(params.get("right_point", "")),
            output_dir=tool_output,
            mode=str(params.get("mode", "alpha")),
            alpha=float(params.get("alpha", 0.5)),
        )

    if tool_id == "video_extract_frames":
        video_path = resolve_user_path(root_dir, params.get("video_path", ""))
        return extract_frames(
            video_path=video_path,
            output_dir=tool_output / video_path.stem / "frames",
            start_time=float(params.get("start_time", 0)),
            end_time=float(params.get("end_time", 3)),
            roi=parse_roi(params.get("roi")),
        )

    if tool_id == "video_make_gif":
        video_path = resolve_user_path(root_dir, params.get("video_path", ""))
        return create_gif(
            video_path=video_path,
            output_dir=tool_output / video_path.stem / "gifs",
            start_time=float(params.get("start_time", 0)),
            end_time=float(params.get("end_time", 3)),
            roi=parse_roi(params.get("roi")),
        )

    if tool_id == "video_convert_web":
        if not selected:
            raise ValueError("Seleziona almeno un video.")
        return {"results": [convert_for_web(path, tool_output / path.stem) for path in selected]}

    if tool_id == "gopro_convert":
        video_path = resolve_user_path(root_dir, params.get("video_path", ""))
        return convert_gopro(
            video_path=video_path,
            output_dir=tool_output / video_path.stem,
            resolution=params.get("resolution"),
            codec=str(params.get("codec", "libx264")),
            crf=int(params.get("crf", 23)),
            preset=str(params.get("preset", "medium")),
        )

    if tool_id == "bird_audio_batch":
        files = selected
        if not files and params.get("audio_path"):
            files = [resolve_user_path(root_dir, params.get("audio_path", ""))]
        if not files:
            raise ValueError("Seleziona almeno un file audio.")
        return run_birdnet_batch(
            files=files,
            output_dir=tool_output,
            latitude=float(params.get("lat", 45.65423642845939)),
            longitude=float(params.get("lon", 13.812502298723128)),
            min_confidence=float(params.get("min_confidence", 0.7)),
            export_clips=bool(params.get("export_clips", True)),
            clip_span=str(params.get("clip_span", "detection")),
        )

    if tool_id == "bird_audio_denoise":
        audio_path = resolve_user_path(root_dir, params.get("audio_path", ""))
        return run_birdnet_denoise(
            audio_path=audio_path,
            output_dir=tool_output / audio_path.stem,
            high_pass_hz=float(params.get("high_pass_hz", 500.0)),
            noise_reduction_factor=float(params.get("noise_reduction_factor", 2.0)),
        )

    if tool_id == "bird_audio_live":
        action = str(params.get("action", "status"))
        live_dir = tool_output / "live"
        if action == "start":
            return start_live_process(
                detections_dir=live_dir,
                backend=str(params.get("backend", "sounddevice")),
                device_index=int(params.get("device_index", 17)),
                min_confidence=float(params.get("min_confidence", 0.1)),
                frame_length=int(params.get("frame_length", 512)),
                slice_interval=int(params.get("slice_interval", 300)),
                disable_denoise=bool(params.get("disable_denoise", True)),
                verbose=bool(params.get("verbose", True)),
            )
        if action == "stop":
            return stop_live_process()
        return live_status()

    raise ValueError(f"Tool non supportato: {tool_id}")
