<#
.SYNOPSIS
  Let another machine on this network SSH into this one.

.DESCRIPTION
  Starts the OpenSSH server, opens port 22, and installs a public key. Run it
  from an ELEVATED PowerShell - every step below needs administrator.

  Key authentication, not a password, because the LTTS account has no password
  and Windows OpenSSH refuses password auth for blank-password accounts. That
  is also how the devkit is reached, so it is the same habit.

  The key file matters more than it looks. For an account in Administrators,
  Windows OpenSSH ignores ~/.ssh/authorized_keys and reads
  C:\ProgramData\ssh\administrators_authorized_keys - and it ignores THAT too
  unless the file is owned by Administrators/SYSTEM with no other write access.
  Both are handled here.

.EXAMPLE
  .\tools\enable-ssh.ps1 -PublicKey "$HOME\Downloads\laptop.pub"
  .\tools\enable-ssh.ps1 -PublicKey "ssh-ed25519 AAAAC3Nza... me@laptop"
  .\tools\enable-ssh.ps1 -Undo
#>
[CmdletBinding()]
param(
    # A .pub file, or the key text itself. Omit to only start the server.
    [string]$PublicKey,
    # Turn it all off again: stop the service, remove the firewall rule.
    [switch]$Undo,
    # Leave cmd.exe as the shell instead of PowerShell.
    [switch]$KeepCmdShell
)

$ErrorActionPreference = "Stop"

function Say($text, $colour = "Gray") { Write-Host $text -ForegroundColor $colour }
function Head($text) { Write-Host ""; Write-Host $text -ForegroundColor Cyan }

$admin = ([Security.Principal.WindowsPrincipal] `
          [Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Say "This needs administrator." Red
    Say "  Right-click PowerShell -> Run as administrator, then run it again." Gray
    exit 1
}

# ------------------------------------------------------------------- undo
if ($Undo) {
    Head "Turning SSH off"
    Stop-Service sshd -ErrorAction SilentlyContinue
    Set-Service sshd -StartupType Disabled -ErrorAction SilentlyContinue
    Remove-NetFirewallRule -Name "assist-sshd" -ErrorAction SilentlyContinue
    Say "  service stopped and disabled, firewall rule removed" Green
    Say "  keys in C:\ProgramData\ssh\administrators_authorized_keys were left alone." DarkGray
    exit 0
}

# ------------------------------------------------------------------ server
Head "OpenSSH server"
if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) {
    Say "  not installed - fetching the Windows capability" Gray
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
}
Set-Service sshd -StartupType Automatic
Start-Service sshd
Say "  sshd $((Get-Service sshd).Status), starts automatically from now on" Green

if (-not $KeepCmdShell) {
    # Otherwise every session lands in cmd.exe, and every command in this repo
    # is PowerShell.
    New-Item -Path "HKLM:\SOFTWARE\OpenSSH" -Force | Out-Null
    New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell `
        -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" `
        -PropertyType String -Force | Out-Null
    Say "  default shell: PowerShell" Green
}

# ---------------------------------------------------------------- firewall
Head "Firewall"
# -Profile Any on purpose: this Wi-Fi is classified Public, and a rule left on
# the default profiles would be enabled and still not apply.
Remove-NetFirewallRule -Name "assist-sshd" -ErrorAction SilentlyContinue
New-NetFirewallRule -Name "assist-sshd" -DisplayName "OpenSSH Server (assist)" `
    -Enabled True -Direction Inbound -Protocol TCP -Action Allow `
    -LocalPort 22 -Profile Any | Out-Null
Say "  port 22 open on every profile (this network is classified Public)" Green

# --------------------------------------------------------------------- key
if ($PublicKey) {
    Head "Public key"
    $key = if (Test-Path $PublicKey) { (Get-Content $PublicKey -Raw).Trim() }
           else { $PublicKey.Trim() }
    if ($key -notmatch '^(ssh-ed25519|ssh-rsa|ecdsa-)') {
        Say "  that does not look like a public key - expected it to start" Red
        Say "  with ssh-ed25519 or ssh-rsa. Nothing was written." Red
        exit 1
    }

    # Administrators get their keys from here, not from the home directory.
    $path = "C:\ProgramData\ssh\administrators_authorized_keys"
    $existing = if (Test-Path $path) { Get-Content $path } else { @() }
    if ($existing -contains $key) {
        Say "  already installed" Gray
    } else {
        Add-Content -Path $path -Value $key -Encoding utf8
        Say "  added to $path" Green
    }

    # sshd silently ignores this file if anyone else can write to it.
    icacls $path /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F" | Out-Null
    Say "  permissions locked to Administrators and SYSTEM" Green
} else {
    Head "Public key"
    Say "  none given. The LTTS account has no password, and Windows OpenSSH" Yellow
    Say "  refuses password logins for blank-password accounts - so nothing" Yellow
    Say "  can sign in yet. On the other laptop:" Yellow
    Say ""
    Say "    ssh-keygen -t ed25519" Gray
    Say "    type `$env:USERPROFILE\.ssh\id_ed25519.pub" Gray
    Say ""
    Say "  then re-run this with -PublicKey `"<that line>`"" Yellow
}

# ------------------------------------------------------------------- where
Head "Connect from the other laptop"
$ips = Get-NetIPAddress -AddressFamily IPv4 |
       Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' }
foreach ($ip in $ips) {
    Say ("  ssh {0}@{1}     ({2})" -f $env:USERNAME, $ip.IPAddress, $ip.InterfaceAlias)
}
Say ""
Say "  Then, to drive the app from there:" DarkGray
Say "    cd C:\simulator\assist; .\run.ps1        # the window opens on THAT screen," DarkGray
Say "                                             # the rig's, not yours" DarkGray
Say "    Get-Content logs\app.log -Wait -Tail 40  # follow it from here" DarkGray
