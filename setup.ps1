<#
.SYNOPSIS
  One-time setup on a fresh machine.

.DESCRIPTION
  Creates the virtual environment, installs Python and Node dependencies,
  fetches the speech voice, and builds the interface. Safe to re-run - it skips
  whatever is already done.

  Afterwards:  .\run.ps1

.EXAMPLE
  .\setup.ps1
  .\setup.ps1 -Devkit http://192.168.1.50:8090
  .\setup.ps1 -NoVoice          Skip the 60 MB voice download
#>
[CmdletBinding()]
param(
    [string]$Devkit,
    [switch]$NoVoice,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Head($t) { Write-Host ""; Write-Host $t -ForegroundColor Cyan }
function Say($t, $c = "Gray") { Write-Host "  $t" -ForegroundColor $c }

Head "DEERE ASSIST - setup"

# ------------------------------------------------------------------ toolchain
Head "Checking the toolchain"
$missing = @()
foreach ($t in @("python", "node", "npm")) {
    $found = Get-Command $t -ErrorAction SilentlyContinue
    if ($found) {
        $v = & $t --version 2>&1 | Select-Object -First 1
        Say ("{0,-8} {1}" -f $t, $v) Green
    } else {
        Say "$t NOT FOUND" Red
        $missing += $t
    }
}
if ($missing.Count) {
    Say ""
    Say "Install the missing tools first:" Yellow
    Say "  python 3.11+   https://python.org/downloads" DarkGray
    Say "  node 20+       https://nodejs.org" DarkGray
    exit 1
}

# ------------------------------------------------------------------- python
Head "Python environment"
if ($Force -and (Test-Path ".venv")) { Remove-Item -Recurse -Force .venv }
if (-not (Test-Path ".venv")) {
    python -m venv .venv
    Say "created .venv" Green
} else {
    Say ".venv already present" DarkGray
}
$Python = ".\.venv\Scripts\python.exe"
& $Python -m pip install --quiet --upgrade pip
Say "installing dependencies (this takes a few minutes the first time)..."
& $Python -m pip install --quiet -e ".[dev]"
& $Python -m pip install --quiet openwakeword onnxruntime sounddevice faster-whisper piper-tts numpy
if ($LASTEXITCODE -ne 0) { Say "pip install failed" Red; exit 1 }
Say "Python dependencies installed" Green

# -------------------------------------------------------------------- voice
Head "Speech voice"
$voiceDir = "assets\voice"
$voice = "$voiceDir\en_US-lessac-medium.onnx"
if ($NoVoice) {
    Say "skipped (-NoVoice). Answers will not be read aloud." Yellow
}
elseif (Test-Path $voice) {
    Say "already downloaded" DarkGray
}
else {
    New-Item -ItemType Directory -Force $voiceDir | Out-Null
    $base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"
    try {
        Say "downloading en_US-lessac-medium (~60 MB)..."
        Invoke-WebRequest "$base/en_US-lessac-medium.onnx" -OutFile $voice -UseBasicParsing
        Invoke-WebRequest "$base/en_US-lessac-medium.onnx.json" -OutFile "$voice.json" -UseBasicParsing
        Say ("downloaded {0:N1} MB" -f ((Get-Item $voice).Length / 1MB)) Green
    }
    catch {
        Say "download failed: $_" Yellow
        Say "The app still runs; it just will not speak." DarkGray
        Say "Fetch it later from $base" DarkGray
    }
}

# ---------------------------------------------------------------- interface
Head "Interface"
# npm and vite write progress and warnings to stderr even on success, and
# under $ErrorActionPreference = "Stop" PowerShell treats a native
# command's stderr as terminating. Success is judged by the built file
# below, not by chatter on stderr.
$savedEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
Push-Location ui
if ($Force -and (Test-Path "node_modules")) { Remove-Item -Recurse -Force node_modules }
if (-not (Test-Path "node_modules")) {
    Say "installing Node packages (a few minutes the first time)..."
    npm install --silent 2>&1 | Out-Null
} else {
    Say "node_modules already present" DarkGray
}
Say "building..."
$buildOutput = npm run build 2>&1 | Out-String
Pop-Location
$ErrorActionPreference = $savedEAP
if ($buildOutput -match "built in ([\d.]+\w+)") { Say "built in $($Matches[1])" DarkGray }
if (-not (Test-Path "ui\dist\index.html")) { Say "interface build failed" Red; exit 1 }
Say "interface built" Green

# ------------------------------------------------------------------- devkit
Head "Devkit"
if ($Devkit) {
    Set-Content -Path ".env" -Value "ASSIST_DEVKIT_URL=$Devkit" -Encoding utf8
    Say "wrote .env -> $Devkit" Green
} else {
    Say "using the default in assist_desktop\config.py" DarkGray
    Say "override any time:  .\run.ps1 -Devkit http://<board-ip>:8090" DarkGray
}

# ------------------------------------------------------------------- verify
Head "Verifying"
& $Python tools\preflight.py --local-only

Head "Done"
Say "Start it with:   .\run.ps1" Green
Say "Watch the logs:  .\logs.ps1" Gray
