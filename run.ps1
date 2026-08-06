<#
.SYNOPSIS
  Start DEERE ASSIST with everything visible.

.DESCRIPTION
  Runs in the FOREGROUND and streams the log to this window. Ctrl-C stops it.
  Nothing is hidden or detached - closing this window closes the application.

.EXAMPLE
  .\run.ps1                 Check the board, then start the app
  .\run.ps1 -Check          Preflight only, change nothing
  .\run.ps1 -Fake           Run against the fixture replayer, no devkit needed
  .\run.ps1 -Build          Rebuild the interface first
  .\run.ps1 -Sensitive      Lower the wake-word threshold for this run
#>
[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$Fake,
    [switch]$Build,
    [switch]$Sensitive,
    [string]$Devkit = "http://192.168.94.180:8090",
    [string]$BoardPassword = $env:ASSIST_BOARD_PASSWORD
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Python = ".\.venv\Scripts\python.exe"

function Say($text, $colour = "Gray") { Write-Host $text -ForegroundColor $colour }
function Head($text) { Write-Host ""; Write-Host $text -ForegroundColor Cyan }

Head "DEERE ASSIST"
Say  "  working dir  $PSScriptRoot"

if (-not (Test-Path $Python)) {
    Say "  no virtual environment. Run: python -m venv .venv" Red
    exit 1
}

# ---------------------------------------------------------------- interface
$dist = "ui\dist\index.html"
if ($Build -or -not (Test-Path $dist)) {
    Head "Building the interface"
    Push-Location ui
    npm run build
    if ($LASTEXITCODE -ne 0) { Pop-Location; Say "  build failed" Red; exit 1 }
    Pop-Location
    Say "  built" Green
}

# --------------------------------------------------------------------- board
if ($Fake) {
    $Devkit = "http://127.0.0.1:8100"
    Head "Fixture replayer"
    Say  "  starting on port 8100 (no devkit needed)"
    $fake = Start-Process -FilePath $Python -ArgumentList "tools\fake_devkit.py" `
                          -PassThru -WindowStyle Minimized
    Start-Sleep -Seconds 3
    Say  "  running as pid $($fake.Id)" Green
}
else {
    Head "Board"
    try {
        $health = Invoke-RestMethod -Uri "$Devkit/health" -TimeoutSec 8
        if ($health.ready) {
            Say ("  ready   {0}   {1} chunks   up {2}s" -f `
                 $health.render_version, $health.chunk_count, $health.uptime_s) Green
        } else {
            Say "  warming up - the interface will say so until it finishes" Yellow
        }
    }
    catch {
        Say "  NOT RESPONDING at $Devkit" Red
        Say "  Start it on the board with:" Gray
        Say "    ssh sima@192.168.94.180" DarkGray
        Say "    cd /media/nvme/ari_assist/v3 && setsid nohup \" DarkGray
        Say "      /media/nvme/ari_jd/venv/bin/python -m uvicorn service_v3:app \" DarkGray
        Say "      --host 0.0.0.0 --port 8090 --app-dir /media/nvme/ari_assist \" DarkGray
        Say "      >../rag_v3.log 2>&1 &" DarkGray
        Say ""
        Say "  Or run without it:  .\run.ps1 -Fake" Gray
        if (-not $Check) { exit 1 }
    }
}

# ------------------------------------------------------------------- devices
Head "Microphone"
& $Python -c @"
from assist_desktop.audio.mic import list_input_devices
ds = list_input_devices()
if not ds:
    print('  none found - voice will be unavailable')
for d in ds[:3]:
    print('  [%d] %s%s' % (d['index'], d['name'][:46], '  <- default' if d['default'] else ''))
"@

$holders = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
           Where-Object { $_.CommandLine -like "*voice_debug*" }
if ($holders) {
    Say "  WARNING: the debug window is open and holds the microphone." Yellow
    Say "           Close it or voice will not start." Yellow
}

if ($Check) { Head "Check only - nothing started"; exit 0 }

# ---------------------------------------------------------------- stale apps
$stale = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
         Where-Object { $_.CommandLine -like "*assist_desktop*" }
foreach ($p in $stale) {
    Say "  stopping previous instance (pid $($p.ProcessId))" DarkGray
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
if ($stale) { Start-Sleep -Seconds 2 }

# ----------------------------------------------------------------- wake word
if ($Sensitive) {
    $env:ASSIST_WAKE_THRESHOLD = "0.45"
    $env:ASSIST_WAKE_FRAMES = "2"
    Head "Wake word"
    Say  "  sensitive mode: threshold 0.45, 2 frames (more false triggers)" Yellow
}

# --------------------------------------------------------------------- start
Head "Starting"
Say  "  devkit    $Devkit"
Say  "  log file  $PSScriptRoot\logs\app.log"
Say  ""
Say  "  Ctrl-C here, or closing the window, stops everything." DarkGray
Write-Host ("-" * 78) -ForegroundColor DarkGray

try {
    & $Python -m assist_desktop --devkit $Devkit
}
finally {
    Write-Host ("-" * 78) -ForegroundColor DarkGray
    if ($fake) {
        Stop-Process -Id $fake.Id -Force -ErrorAction SilentlyContinue
        Say "  fixture replayer stopped" DarkGray
    }
    Say "  stopped." Gray
}
