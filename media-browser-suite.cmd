@echo off
setlocal
set "REPO_ROOT=%~dp0"
set "INSTALLED_PYTHON=%LOCALAPPDATA%\MediaBrowserSuite\venv\Scripts\python.exe"
set "VENV_PYTHON=%REPO_ROOT%.venv\Scripts\python.exe"
set "MEDIA_BROWSER_OPEN=1"

if exist "%INSTALLED_PYTHON%" (
  "%INSTALLED_PYTHON%" -m media_suite %*
  exit /b %ERRORLEVEL%
)

if not exist "%VENV_PYTHON%" (
  echo Installazione non trovata in "%LOCALAPPDATA%\MediaBrowserSuite".
  echo In alternativa non trovo neppure un virtual environment locale in "%REPO_ROOT%.venv".
  echo Esegui prima:
  echo   powershell -ExecutionPolicy Bypass -File "%REPO_ROOT%install.ps1"
  exit /b 1
)

"%VENV_PYTHON%" -m media_suite %*
