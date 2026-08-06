<#
.SYNOPSIS
  Watch the logs live.

.DESCRIPTION
  Follows the application log, colouring the lines that matter. Run it in a
  second window next to .\run.ps1 - or on its own, since the log survives
  restarts.

.EXAMPLE
  .\logs.ps1                Follow the application log
  .\logs.ps1 -Voice         Only wake word, transcripts and audio
  .\logs.ps1 -Board         Follow the board's service log instead
  .\logs.ps1 -Tail 200      Show more history before following
#>
[CmdletBinding()]
param(
    [switch]$Voice,
    [switch]$Board,
    [int]$Tail = 40,
    [string]$BoardHost = "192.168.94.180",
    [string]$BoardPassword = $env:ASSIST_BOARD_PASSWORD
)

Set-Location $PSScriptRoot

if ($Board) {
    $plink = "C:\Program Files\PuTTY\plink.exe"
    if (-not (Test-Path $plink)) { Write-Host "plink not found" -ForegroundColor Red; exit 1 }
    if (-not $BoardPassword) {
        Write-Host 'Set $env:ASSIST_BOARD_PASSWORD first.' -ForegroundColor Red; exit 1
    }
    $key = "SHA256:PgQIqx43Xlf1bLiYq7F9gp7YEx1afGr4TxH3vGzF66A"
    Write-Host "Following the board's manual service (Ctrl-C to stop)" -ForegroundColor Cyan
    & $plink -batch -ssh -hostkey $key -pw $BoardPassword "sima@$BoardHost" `
        "tail -n $Tail -F /media/nvme/ari_assist/rag_v3.log"
    exit
}

$log = Join-Path $PSScriptRoot "logs\app.log"
if (-not (Test-Path $log)) {
    New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
    New-Item -ItemType File $log | Out-Null
    Write-Host "No log yet - waiting for the app to start..." -ForegroundColor DarkGray
}

Write-Host ""
if ($Voice) {
    Write-Host "Voice only - wake word, transcripts, audio (Ctrl-C to stop)" -ForegroundColor Cyan
    Write-Host 'Say "hey chris" and watch for WAKE or "near miss".' -ForegroundColor DarkGray
} else {
    Write-Host "Application log (Ctrl-C to stop)" -ForegroundColor Cyan
}
Write-Host ("-" * 78) -ForegroundColor DarkGray

Get-Content $log -Tail $Tail -Wait | ForEach-Object {
    $line = $_
    if ($Voice -and $line -notmatch "wake|audio|voice|WAKE|near miss|heard") { return }

    $colour = switch -Regex ($line) {
        "WAKE "                     { "Green";      break }
        "near miss"                 { "Yellow";     break }
        "heard "                    { "Cyan";       break }
        "ERROR|FAILED|Traceback"    { "Red";        break }
        "WARN"                      { "Yellow";     break }
        "ask \("                    { "White";      break }
        "devkit (offline|warming)"  { "Yellow";     break }
        "devkit ready"              { "Green";      break }
        default                     { "Gray" }
    }
    Write-Host $line -ForegroundColor $colour
}
