from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _managed_home() -> Path:
    override = os.environ.get("MEDIA_TOOLS_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "MediaTools"
        return Path.home() / "AppData" / "Local" / "MediaTools"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MediaTools"
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "media-tools"
    return Path.home() / ".local" / "share" / "media-tools"


MANAGED_HOME = _managed_home()
VENV_DIR = MANAGED_HOME / "venv"


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _run(command: list[str], env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=REPO_ROOT, env=env, check=True)


def _managed_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    if extra:
        env.update(extra)
    return env


def ensure_installed(include_dev: bool = True) -> Path:
    python_path = _venv_python()
    if not python_path.exists():
        VENV_DIR.parent.mkdir(parents=True, exist_ok=True)
        builder = venv.EnvBuilder(with_pip=True)
        builder.create(VENV_DIR)
    _run([str(python_path), "-m", "pip", "install", "--upgrade", "pip"])
    target = ".[dev]" if include_dev else "."
    _run([str(python_path), "-m", "pip", "install", "--upgrade", "--editable", target])
    return python_path


def install_command() -> int:
    python_path = ensure_installed(include_dev=True)
    print(f"Media Tools installato in editable mode usando il repository: {REPO_ROOT}")
    print(f"Home runtime gestita: {MANAGED_HOME}")
    print(f"Virtual environment gestito: {VENV_DIR}")
    print(f"Python gestito: {python_path}")
    return 0


def _spawn_managed(args: list[str], env: dict[str, str] | None = None) -> int:
    python_path = _venv_python()
    if not python_path.exists():
        raise SystemExit("Virtual environment non trovato. Esegui prima `make install`.")
    completed = subprocess.run([str(python_path), *args], cwd=REPO_ROOT, env=_managed_env(env), check=False)
    return completed.returncode


def run_command(dev: bool = False) -> int:
    env = {
        "MEDIA_TOOLS_OPEN": os.environ.get("MEDIA_TOOLS_OPEN", "1"),
    }
    if dev:
        env["MEDIA_TOOLS_PORT"] = os.environ.get("MEDIA_TOOLS_PORT", "8766")
    else:
        env["MEDIA_TOOLS_PORT"] = os.environ.get("MEDIA_TOOLS_PORT", "8765")
    return _spawn_managed(["-m", "media_tools"], env=env)


def test_command() -> int:
    return _spawn_managed(["-m", "pytest", "tests"], env={"PYTHONUNBUFFERED": "1"})


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    command = args[0] if args else "dev"

    if command == "install":
        return install_command()
    if command == "run":
        return run_command(dev=False)
    if command == "dev":
        return run_command(dev=True)
    if command == "test":
        return test_command()

    raise SystemExit(f"Comando non supportato: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
