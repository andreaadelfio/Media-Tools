@echo off
setlocal
set "REPO_ROOT=%~dp0"
set "VENV_PYTHON=%LOCALAPPDATA%\MediaTools\venv\Scripts\python.exe"
set "MEDIA_TOOLS_OPEN=1"
if "%MEDIA_TOOLS_PORT%"=="" set "MEDIA_TOOLS_PORT=8766"
set "PYTHONPATH=%REPO_ROOT%"

if not exist "%VENV_PYTHON%" (
  echo Installazione non trovata in "%LOCALAPPDATA%\MediaTools".
  echo Esegui prima:
  echo   powershell -ExecutionPolicy Bypass -File "%REPO_ROOT%install.ps1"
  exit /b 1
)

pushd "%REPO_ROOT%"
"%VENV_PYTHON%" -m media_tools %*
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
