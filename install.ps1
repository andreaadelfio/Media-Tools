$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
$localAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { [Environment]::GetFolderPath("LocalApplicationData") }
$installRoot = Join-Path $localAppData "MediaBrowserSuite"
$venvPath = Join-Path $installRoot "venv"
$userBinDir = Join-Path $HOME ".local\bin"
$globalLauncherPath = Join-Path $userBinDir "media-browser-suite.cmd"
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue

if (-not $pythonCmd) {
    throw "Python non trovato nel PATH. Installa Python e riprova."
}

New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
New-Item -ItemType Directory -Force -Path $userBinDir | Out-Null

if (-not (Test-Path $venvPath)) {
    Write-Host "Creo il virtual environment in $venvPath"
    & $pythonCmd.Source -m venv $venvPath
}

$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvPip = Join-Path $venvPath "Scripts\pip.exe"

Write-Host "Aggiorno pip"
& $venvPython -m pip install --upgrade pip

Write-Host "Installo Media Browser Suite in $installRoot"
& $venvPip install --upgrade $repoRoot

$launcherContent = @"
@echo off
setlocal
set "APP_ROOT=$installRoot"
set "VENV_PYTHON=%APP_ROOT%\venv\Scripts\python.exe"
set "MEDIA_BROWSER_OPEN=1"

if not exist "%VENV_PYTHON%" (
  echo Installazione di Media Browser Suite non trovata in "%APP_ROOT%".
  echo Esegui di nuovo l'installer dal repository.
  exit /b 1
)

"%VENV_PYTHON%" -m media_suite %*
"@

Set-Content -Path $globalLauncherPath -Value $launcherContent -Encoding ASCII

$currentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$userPathEntries = @()
if ($currentUserPath) {
    $userPathEntries = $currentUserPath.Split(";") | Where-Object { $_ }
}

$pathAlreadyPresent = $false
foreach ($entry in $userPathEntries) {
    if ([StringComparer]::OrdinalIgnoreCase.Equals($entry.TrimEnd('\'), $userBinDir.TrimEnd('\'))) {
        $pathAlreadyPresent = $true
        break
    }
}

if (-not $pathAlreadyPresent) {
    $newUserPath = if ($currentUserPath) { "$currentUserPath;$userBinDir" } else { $userBinDir }
    [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
    Write-Host "Aggiungo $userBinDir al PATH utente"
}

$processPathEntries = $env:Path -split ";"
$processHasUserBin = $false
foreach ($entry in $processPathEntries) {
    if ([StringComparer]::OrdinalIgnoreCase.Equals($entry.TrimEnd('\'), $userBinDir.TrimEnd('\'))) {
        $processHasUserBin = $true
        break
    }
}

if (-not $processHasUserBin) {
    $env:Path = "$userBinDir;$env:Path"
}

Write-Host ""
Write-Host "Installazione completata."
Write-Host "Cartella installazione:"
Write-Host "  $installRoot"
Write-Host ""
Write-Host "Launcher globale:"
Write-Host "  $globalLauncherPath"
Write-Host ""
Write-Host "Da un nuovo terminale puoi usare:"
Write-Host "  media-browser-suite"
Write-Host ""
Write-Host "Nel terminale corrente puoi gia usare:"
Write-Host "  $globalLauncherPath"
Write-Host ""
Write-Host "Launcher del repository ancora disponibili:"
Write-Host "  $repoRoot\run_media_browser_suite.bat"
Write-Host "  $repoRoot\media-browser-suite.cmd"
