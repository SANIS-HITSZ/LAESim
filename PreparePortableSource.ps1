[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DestinationRoot
)

$ErrorActionPreference = "Stop"

$sourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceRoot = (Resolve-Path $sourceRoot).Path

if (Test-Path -LiteralPath $DestinationRoot) {
    $destItem = Get-Item -LiteralPath $DestinationRoot
    if ($destItem.PSIsContainer -and (Get-ChildItem -LiteralPath $DestinationRoot -Force | Measure-Object).Count -gt 0) {
        throw "DestinationRoot must be empty or not exist: $DestinationRoot"
    }
} else {
    New-Item -ItemType Directory -Path $DestinationRoot | Out-Null
}

$excludeDirNames = @(
    ".git",
    ".vs",
    "Binaries",
    "Build",
    "Intermediate",
    "Saved",
    "temp",
    "__pycache__"
)

$excludeFileNames = @(
    "*.obj",
    "*.ipdb",
    "*.iobj",
    "*.ilk",
    "*.lib",
    "*.exp",
    "*.pdb",
    "*.tlog",
    "*.log",
    "*.tmp",
    "*.suo",
    "*.user",
    "*.VC.db",
    "*.VC.opendb"
)

function ShouldSkipDirectory([System.IO.DirectoryInfo]$directoryInfo) {
    return $excludeDirNames -contains $directoryInfo.Name
}

function ShouldSkipFile([System.IO.FileInfo]$fileInfo) {
    foreach ($pattern in $excludeFileNames) {
        if ($fileInfo.Name -like $pattern) {
            return $true
        }
    }
    return $false
}

function Copy-PortableTree([string]$sourcePath, [string]$destPath) {
    if (-not (Test-Path -LiteralPath $destPath)) {
        New-Item -ItemType Directory -Path $destPath | Out-Null
    }

    Get-ChildItem -LiteralPath $sourcePath -Force | ForEach-Object {
        $targetPath = Join-Path $destPath $_.Name

        if ($_.PSIsContainer) {
            if (ShouldSkipDirectory $_) {
                return
            }

            Copy-PortableTree -sourcePath $_.FullName -destPath $targetPath
            return
        }

        if (ShouldSkipFile $_) {
            return
        }

        Copy-Item -LiteralPath $_.FullName -Destination $targetPath -Force
    }
}

Copy-PortableTree -sourcePath $sourceRoot -destPath (Resolve-Path $DestinationRoot).Path

Write-Host "Portable source tree created at: $DestinationRoot"
Write-Host "Next steps on another PC:"
Write-Host "  1. Install UE 4.27 and Visual Studio 2019 or 2022 with C++ tools."
Write-Host "  2. Run BuildAirSimRelease.bat from the repo root."
Write-Host "  3. Run Unreal\\Environments\\Blocks\\BuildBlocksEditor.bat if UE editor build is needed."
