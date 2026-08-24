$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$InstallDir = Join-Path $env:LOCALAPPDATA "WMS Agent"
$VenvDir = Join-Path $InstallDir "venv"
$Desktop = [Environment]::GetFolderPath("Desktop")
$Launcher = Join-Path $Desktop "WMS Agent.cmd"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$Python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
  $Python = "py"
  $VersionArgs = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  $Python = "python"
  $VersionArgs = @()
} else {
  throw "Python 3.12 or newer is required. Install it from https://www.python.org/downloads/windows/ and rerun this installer."
}

& $Python @VersionArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 'Python 3.12 or newer is required.')"
& $Python @VersionArgs -m venv $VenvDir

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$ClientExe = Join-Path $VenvDir "Scripts\wms-agent-client.exe"

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install $RootDir

$EnvFile = Join-Path $InstallDir ".env"
if (!(Test-Path $EnvFile)) {
  Copy-Item (Join-Path $RootDir ".env.example") $EnvFile
}

@"
@echo off
setlocal
if "%WMS_LOCAL_AGENT_HOST%"=="" set WMS_LOCAL_AGENT_HOST=127.0.0.1
if "%WMS_LOCAL_AGENT_PORT%"=="" set WMS_LOCAL_AGENT_PORT=8787
if "%WMS_LOCAL_AGENT_MODEL_PROVIDER%"=="" set WMS_LOCAL_AGENT_MODEL_PROVIDER=openai-compatible
cd /d "$InstallDir"
"$ClientExe"
"@ | Set-Content -Path $Launcher -Encoding ASCII

Write-Host "WMS Agent installed."
Write-Host "Config: $EnvFile"
Write-Host "Launcher: $Launcher"
