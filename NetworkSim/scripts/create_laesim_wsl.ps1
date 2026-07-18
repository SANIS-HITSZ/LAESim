[CmdletBinding()]
param(
    [string]$DistroName = "LAESim",
    [string]$InstallRoot = "H:\WSL\LAESim",
    [Parameter(Mandatory = $true)]
    [string]$RootfsPath,
    [string]$DefaultUser = "pyq"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($DefaultUser -notmatch '^[a-z_][a-z0-9_-]*$') {
    throw "DefaultUser must be a valid Linux user name."
}

$rootfs = (Resolve-Path -LiteralPath $RootfsPath).Path
$existing = wsl.exe --list --quiet | ForEach-Object { $_ -replace "`0", "" }
if ($existing -contains $DistroName) {
    throw "WSL distribution '$DistroName' already exists."
}

New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
wsl.exe --import $DistroName $InstallRoot $rootfs --version 2
if ($LASTEXITCODE -ne 0) {
    throw "wsl --import failed with exit code $LASTEXITCODE."
}

$setup = @"
set -e
if ! id -u '$DefaultUser' >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash '$DefaultUser'
fi
printf '[boot]\nsystemd=true\n\n[user]\ndefault=$DefaultUser\n\n[interop]\nappendWindowsPath=false\n' >/etc/wsl.conf
"@
wsl.exe -d $DistroName -u root -- bash -lc $setup
if ($LASTEXITCODE -ne 0) {
    throw "Could not configure /etc/wsl.conf."
}

wsl.exe --terminate $DistroName
Write-Host "Created WSL2 distribution '$DistroName' at '$InstallRoot'."
Write-Host "Run: wsl -d $DistroName"
