@echo off
setlocal
set "REPO_ROOT=%~dp0"
set "INSTALLED_PYTHON=%LOCALAPPDATA%\MediaTools\venv\Scripts\python.exe"
set "MEDIA_TOOLS_OPEN=1"

if exist "%INSTALLED_PYTHON%" (
  "%INSTALLED_PYTHON%" -m media_tools %*
  exit /b %ERRORLEVEL%
)

echo Installazione non trovata in "%LOCALAPPDATA%\MediaTools".
echo Esegui prima:
echo   powershell -ExecutionPolicy Bypass -File "%REPO_ROOT%install.ps1"
exit /b 1
