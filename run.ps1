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
  .\run.ps1 -Local          The simulator is on THIS machine: write its command
                            file directly, no window_listener.py needed
#>
[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$Fake,
    [switch]$Build,
    [switch]$Sensitive,
    [switch]$Local,
    # Empty on purpose. This used to default to the v3 address and was passed
    # on every launch, so the flag's default beat .env and editing that file
    # appeared to do nothing at all.
    [string]$Devkit = "",
    [string]$Trigger,
    [string]$BoardPassword = $env:ASSIST_BOARD_PASSWORD
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Python = ".\.venv\Scripts\python.exe"

# Resolve the devkit the way the app does: -Devkit wins, then .env, then a
# built-in fallback. 8090 is the v3 pipeline, 8092 is v4.
$DevkitFromEnv = $false
if (-not $Devkit) {
    if (Test-Path ".env") {
        $line = Select-String -Path ".env" -Pattern '^\s*ASSIST_DEVKIT_URL\s*=' -ErrorAction SilentlyContinue
        if ($line) {
            $Devkit = ($line.Line -split '=', 2)[1].Trim()
            $DevkitFromEnv = $true
        }
    }
    if (-not $Devkit) { $Devkit = "http://192.168.94.180:8090" }
}

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
        # npm and vite write progress and warnings to stderr even on success, and
    # under $ErrorActionPreference = "Stop" PowerShell treats a native
    # command's stderr as terminating. Success is judged by the built file
    # below, not by chatter on stderr.
    $savedEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    Push-Location ui
    npm run build 2>&1 | Out-Null
    Pop-Location
    $ErrorActionPreference = $savedEAP
    if (-not (Test-Path $dist)) { Say "  build failed" Red; exit 1 }
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
# These are set as environment variables, and an environment variable set by
# a previous -Sensitive run outlives that run: it is inherited by every later
# run in the same window. One -Sensitive run then quietly gated every session
# after it at 0.45 -- including ones started without the flag. Clear them, so
# a plain run is a plain run. Set them in .env to make them stick.
if (-not $Sensitive) {
    if ($env:ASSIST_WAKE_THRESHOLD -or $env:ASSIST_WAKE_FRAMES) {
        Head "Wake word"
        Say  "  clearing a leftover sensitive-mode gate from this window" DarkGray
    }
    Remove-Item Env:ASSIST_WAKE_THRESHOLD -ErrorAction SilentlyContinue
    Remove-Item Env:ASSIST_WAKE_FRAMES -ErrorAction SilentlyContinue
}
if ($Sensitive) {
    $env:ASSIST_WAKE_THRESHOLD = "0.7"
    $env:ASSIST_WAKE_FRAMES = "2"
    Head "Wake word"
    Say  "  sensitive mode: threshold 0.7, 2 frames" Yellow
    Say  "  the default is 3 frames above 0.8 - the measured line between" DarkGray
    Say  "  'hey chris' and 'the pressure is fine'. Below it, ordinary" DarkGray
    Say  "  speech opens the microphone on its own." DarkGray
}

# ------------------------------------------------------------------ simulator
# Spoken orders ("fold the boom") are sent here, not to the devkit. This
# overrides .env for one run; edit .env to make it stick.
if ($Trigger) { $env:ASSIST_TRIGGER_URL = $Trigger }

# On one machine there is no network to cross: the order goes straight into the
# file the simulator reads, and window_listener.py does not need to be running.
if ($Local) { $env:ASSIST_TRIGGER_MODE = "local" }

# --------------------------------------------------------------------- start
Head "Starting"
Say  ("  devkit    $Devkit" + $(if ($DevkitFromEnv) { "  (.env)" } else { "" }))
$shownTrigger = $env:ASSIST_TRIGGER_URL
if (-not $shownTrigger -and (Test-Path ".env")) {
    $line = Select-String -Path ".env" -Pattern '^\s*ASSIST_TRIGGER_URL\s*=' -ErrorAction SilentlyContinue
    if ($line) { $shownTrigger = ($line.Line -split '=', 2)[1].Trim() + "  (.env)" }
}
if (-not $shownTrigger) { $shownTrigger = "http://192.168.94.11:5000/trigger  (default)" }
if ($env:ASSIST_TRIGGER_MODE -eq "local") {
    $file = $env:ASSIST_COMMAND_FILE
    if (-not $file) { $file = 'C:\simulator\voice_commands.json' }
    $shownTrigger = "$file  (this machine - no listener needed)"
}
Say  "  simulator $shownTrigger"
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
