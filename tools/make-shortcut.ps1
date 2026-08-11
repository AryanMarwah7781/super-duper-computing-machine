<#
.SYNOPSIS
  Put a DEERE ASSIST icon on the desktop.

.DESCRIPTION
  Builds an .ico from Chris and creates a desktop shortcut that starts the
  app. The shortcut runs run.ps1, so it gets the same preflight, the same
  .env and the same log as launching by hand -- an icon that starts the app a
  second way is an icon that fails differently from the way you tested.

  The icon is generated rather than committed as a binary: chris.png is
  already in the repo and .NET is already on the machine, so a second copy of
  the same artwork would only be one more thing to keep in step.

.EXAMPLE
  .\tools\make-shortcut.ps1
  .\tools\make-shortcut.ps1 -Console      Keep a console window for the log
  .\tools\make-shortcut.ps1 -Remove
#>
[CmdletBinding()]
param(
    # Show the log window. Off by default: for a demo the console is another
    # window on a monitor that is supposed to be showing the app.
    [switch]$Console,
    [switch]$Remove,
    [string]$Name = "DEERE ASSIST",
    # Passed straight through to run.ps1, e.g. "-Build -Sensitive -Local".
    # Baked into the shortcut, so whatever is set here is what every
    # double-click gets -- there is no way to type a flag at an icon.
    [string]$Flags = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath("Desktop")
$link = Join-Path $desktop "$Name.lnk"

if ($Remove) {
    if (Test-Path $link) { Remove-Item $link; Write-Host "Removed $link" }
    else { Write-Host "No shortcut at $link" }
    return
}

# -- the icon --------------------------------------------------------------
$png = Join-Path $root "ui\public\chris.png"
if (-not (Test-Path $png)) { throw "no artwork at $png" }

$icoDir = Join-Path $root "assets"
if (-not (Test-Path $icoDir)) { New-Item -ItemType Directory $icoDir | Out-Null }
$ico = Join-Path $icoDir "assist.ico"

Add-Type -AssemblyName System.Drawing

# 256 is the largest an .ico entry can describe: the width and height fields
# are single bytes, and 0 means 256. The source is 1024, so it must come down
# or the header cannot express it.
$source = [System.Drawing.Image]::FromFile($png)
try {
    $bmp = New-Object System.Drawing.Bitmap 256, 256
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    try {
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.Clear([System.Drawing.Color]::Transparent)
        $g.DrawImage($source, 0, 0, 256, 256)
    } finally { $g.Dispose() }

    $ms = New-Object System.IO.MemoryStream
    try {
        $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
        $pngBytes = $ms.ToArray()
    } finally { $ms.Dispose() }
    $bmp.Dispose()
} finally { $source.Dispose() }

# An .ico is a 6-byte header, one 16-byte entry per image, then the images.
# A PNG payload is allowed since Vista and keeps the alpha channel, which a
# bitmap entry would need a separate mask for.
$out = New-Object System.IO.MemoryStream
$w = New-Object System.IO.BinaryWriter $out
try {
    $w.Write([UInt16]0)          # reserved
    $w.Write([UInt16]1)          # 1 = icon
    $w.Write([UInt16]1)          # one image
    $w.Write([Byte]0)            # width  256, written as 0
    $w.Write([Byte]0)            # height 256
    $w.Write([Byte]0)            # colours in palette: none, it is truecolour
    $w.Write([Byte]0)            # reserved
    $w.Write([UInt16]1)          # colour planes
    $w.Write([UInt16]32)         # bits per pixel
    $w.Write([UInt32]$pngBytes.Length)
    $w.Write([UInt32]22)         # offset: 6 header + 16 entry
    $w.Write($pngBytes)
    $w.Flush()
    [System.IO.File]::WriteAllBytes($ico, $out.ToArray())
} finally { $w.Dispose() }

Write-Host "Icon    $ico"

# -- the shortcut ----------------------------------------------------------
$runner = Join-Path $root "run.ps1"
if (-not (Test-Path $runner)) { throw "no run.ps1 at $runner" }

# -ExecutionPolicy Bypass because the rig's default policy blocks a .ps1
# launched from a shortcut even when the same file runs fine from a prompt.
$psArgs = "-ExecutionPolicy Bypass -File `"$runner`""
if ($Flags.Trim()) { $psArgs = "$psArgs $($Flags.Trim())" }
if ($Console) {
    $target = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $arguments = "-NoExit $psArgs"
} else {
    # conhost --headless keeps the console off the screen without detaching
    # the process, so closing the app still closes everything. `pythonw` was
    # the other option and loses the preflight run.ps1 does.
    $target = "$env:SystemRoot\System32\conhost.exe"
    $arguments = "--headless $env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe -WindowStyle Hidden $psArgs"
}

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($link)
$sc.TargetPath = $target
$sc.Arguments = $arguments
$sc.WorkingDirectory = $root
$sc.IconLocation = "$ico,0"
# ASCII only in this file. PowerShell 5.1 reads a .ps1 as ANSI unless it has
# a BOM, so a stray em dash here is a parse error on the rig even though the
# file is perfectly good UTF-8.
$sc.Description = "DEERE ASSIST - sprayer chatbot, lessons and simulator"
$sc.Save()

Write-Host "Shortcut $link"
if ($Flags.Trim()) { Write-Host "Flags    run.ps1 $($Flags.Trim())" }
else { Write-Host "Flags    none - run.ps1 runs on its defaults" }
Write-Host ""
Write-Host "Double-click it to start. Remove with: .\tools\make-shortcut.ps1 -Remove"
