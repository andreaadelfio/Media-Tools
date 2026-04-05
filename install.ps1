$ErrorActionPreference = "Stop"

function Write-Launcher {
    param(
        [string]$LauncherPath,
        [string]$InstallRoot
    )

    $launcherContent = @"
@echo off
setlocal
set "APP_ROOT=$InstallRoot"
set "VENV_PYTHON=%APP_ROOT%\venv\Scripts\python.exe"
set "MEDIA_TOOLS_OPEN=1"

if not exist "%VENV_PYTHON%" (
  echo Installazione di MediaTools non trovata in "%APP_ROOT%".
  echo Esegui di nuovo l'installer dal repository.
  exit /b 1
)

"%VENV_PYTHON%" -m media_tools %*
"@

    Set-Content -Path $LauncherPath -Value $launcherContent -Encoding ASCII
}

function Sync-SourceSnapshot {
    param(
        [string]$SourceRoot,
        [string]$SnapshotRoot
    )

    New-Item -ItemType Directory -Force -Path $SnapshotRoot | Out-Null
    $logPath = Join-Path $SnapshotRoot "robocopy.log"
    $arguments = @(
        $SourceRoot,
        $SnapshotRoot,
        "/MIR",
        "/XD", ".git", ".venv", "__pycache__", "build", "dist", "workspace", "media_tools_output", "media_tools.egg-info",
        "/XF", "*.pyc", "*.pyo",
        "/R:1",
        "/W:1",
        "/NFL",
        "/NDL",
        "/NP",
        "/NJH",
        "/NJS",
        "/LOG:$logPath"
    )

    & robocopy @arguments | Out-Null
    $robocopyExitCode = $LASTEXITCODE
    if ($robocopyExitCode -ge 8) {
        throw "Copia del sorgente fallita con codice robocopy $robocopyExitCode. Log: $logPath"
    }
}

$repoRoot = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
$localAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { [Environment]::GetFolderPath("LocalApplicationData") }
$installRoot = Join-Path $localAppData "MediaTools"
$venvPath = Join-Path $installRoot "venv"
$sourceSnapshotPath = Join-Path $installRoot "source"
$buildArtifactsPath = Join-Path $installRoot "build-artifacts"
$userBinDir = Join-Path $HOME ".local\bin"
$globalLauncherPaths = @(
    (Join-Path $userBinDir "media-tools.cmd"),
    (Join-Path $userBinDir "media_tools.cmd")
)

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    throw "Python non trovato nel PATH. Installa Python e riprova."
}

New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
New-Item -ItemType Directory -Force -Path $buildArtifactsPath | Out-Null
New-Item -ItemType Directory -Force -Path $userBinDir | Out-Null

Write-Host "Preparo snapshot del repository in $sourceSnapshotPath"
Sync-SourceSnapshot -SourceRoot $repoRoot -SnapshotRoot $sourceSnapshotPath

if (-not (Test-Path $venvPath)) {
    Write-Host "Creo il virtual environment in $venvPath"
    & $pythonCmd.Source -m venv $venvPath
}

$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvPip = Join-Path $venvPath "Scripts\pip.exe"
$venvScriptsDir = Join-Path $venvPath "Scripts"
$pipBuildTrackerPath = Join-Path $buildArtifactsPath "pip-build-tracker"

Write-Host "Aggiorno pip"
& $venvPython -m pip install --upgrade pip

New-Item -ItemType Directory -Force -Path $pipBuildTrackerPath | Out-Null
$env:PIP_BUILD_TRACKER = $pipBuildTrackerPath

Write-Host "Installo MediaTools in $installRoot"
Push-Location $sourceSnapshotPath
try {
    & $venvPip install --upgrade .
}
finally {
    Pop-Location
}

foreach ($launcherPath in $globalLauncherPaths) {
    Write-Launcher -LauncherPath $launcherPath -InstallRoot $installRoot
}

$currentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$userPathEntries = @()
if ($currentUserPath) {
    $userPathEntries = $currentUserPath.Split(";") | Where-Object { $_ }
}

$pathsToAdd = @($userBinDir, $venvScriptsDir)
foreach ($pathToAdd in $pathsToAdd) {
    $pathAlreadyPresent = $false
    foreach ($entry in $userPathEntries) {
        if ([StringComparer]::OrdinalIgnoreCase.Equals($entry.TrimEnd('\'), $pathToAdd.TrimEnd('\'))) {
            $pathAlreadyPresent = $true
            break
        }
    }

    if (-not $pathAlreadyPresent) {
        $currentUserPath = if ($currentUserPath) { "$currentUserPath;$pathToAdd" } else { $pathToAdd }
        $userPathEntries += $pathToAdd
        Write-Host "Aggiungo $pathToAdd al PATH utente"
    }
}

[Environment]::SetEnvironmentVariable("Path", $currentUserPath, "User")

$processPathEntries = $env:Path -split ";"
foreach ($pathToAdd in $pathsToAdd) {
    $processHasPath = $false
    foreach ($entry in $processPathEntries) {
        if ([StringComparer]::OrdinalIgnoreCase.Equals($entry.TrimEnd('\'), $pathToAdd.TrimEnd('\'))) {
            $processHasPath = $true
            break
        }
    }

    if (-not $processHasPath) {
        $env:Path = "$pathToAdd;$env:Path"
    }
}

Write-Host ""
Write-Host "Installazione completata."
Write-Host "Cartella installazione:"
Write-Host "  $installRoot"
Write-Host ""
Write-Host "Snapshot sorgente usato per l'installazione:"
Write-Host "  $sourceSnapshotPath"
Write-Host ""
Write-Host "Artefatti build / egg-info:"
Write-Host "  $buildArtifactsPath"
Write-Host "  $sourceSnapshotPath\media_tools.egg-info"
Write-Host ""
Write-Host "Launcher globali:"
foreach ($launcherPath in $globalLauncherPaths) {
    Write-Host "  $launcherPath"
}
Write-Host ""
Write-Host "Da un nuovo terminale puoi usare:"
Write-Host "  media-tools"
Write-Host "  media_tools"
Write-Host ""
Write-Host "Nel terminale corrente puoi gia usare:"
foreach ($launcherPath in $globalLauncherPaths) {
    Write-Host "  $launcherPath"
}
