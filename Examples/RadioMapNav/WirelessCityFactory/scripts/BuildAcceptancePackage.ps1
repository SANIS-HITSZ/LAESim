param(
    [string]$OutputDirectory = "",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
if (-not $OutputDirectory) {
    $OutputDirectory = Split-Path -Parent $repositoryRoot
}
$outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

$pythonCandidates = @(
    (Join-Path $repositoryRoot ".venv\Scripts\python.exe"),
    (Join-Path $repositoryRoot ".venv-sionna310\Scripts\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $python) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $launcher) {
        throw "Python was not found. Install Python 3.10+ or create .venv before packaging."
    }
    $python = $launcher.Source
}

if (-not $SkipTests) {
    Write-Host "Running test suite before packaging..."
    $env:PYTHONPATH = Join-Path $repositoryRoot "src"
    if ([System.IO.Path]::GetFileName($python) -ieq "py.exe") {
        & $python -3.10 -m pytest $repositoryRoot
    } else {
        & $python -m pytest $repositoryRoot
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Tests failed; no acceptance package was created."
    }
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$packageName = "WirelessCityFactory-Acceptance-$stamp"
$stagingRoot = Join-Path $outputRoot (".{0}.staging-{1}" -f $packageName, [guid]::NewGuid().ToString("N"))
$packageRoot = Join-Path $stagingRoot "WirelessCityFactory"
$zipPath = Join-Path $outputRoot "$packageName.zip"
$hashPath = "$zipPath.sha256.txt"

$resolvedOutputPrefix = $outputRoot.TrimEnd('\') + '\'
$resolvedStaging = [System.IO.Path]::GetFullPath($stagingRoot)
if (-not $resolvedStaging.StartsWith($resolvedOutputPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to create staging directory outside the requested output directory."
}

function Copy-Tree {
    param([string]$RelativePath)
    $source = Join-Path $repositoryRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Required path is missing: $RelativePath"
    }
    $destination = Join-Path $packageRoot $RelativePath
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
}

try {
    New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null

    foreach ($file in @(".gitignore", "LICENSE", "PROVENANCE.md", "README.md", "pyproject.toml")) {
        Copy-Item -LiteralPath (Join-Path $repositoryRoot $file) -Destination (Join-Path $packageRoot $file) -Force
    }
    foreach ($directory in @("configs", "docs", "scripts", "src", "tests")) {
        Copy-Tree $directory
    }

    $ueRoot = Join-Path $packageRoot "unreal\WirelessCityFactory"
    New-Item -ItemType Directory -Path $ueRoot -Force | Out-Null
    foreach ($file in @("README.md", "WirelessCityFactory.uproject")) {
        Copy-Item -LiteralPath (Join-Path $repositoryRoot "unreal\WirelessCityFactory\$file") -Destination (Join-Path $ueRoot $file) -Force
    }
    foreach ($directory in @("Config", "Scripts", "Source")) {
        Copy-Tree "unreal\WirelessCityFactory\$directory"
    }

    Get-ChildItem -LiteralPath $packageRoot -Recurse -Directory -Force |
        Where-Object { $_.Name -in @("__pycache__", ".pytest_cache", ".ruff_cache") } |
        Sort-Object FullName -Descending |
        Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $packageRoot -Recurse -File -Force |
        Where-Object { $_.Name -like "*.bak-*" -or $_.Extension -in @(".pyc", ".pyo") } |
        Remove-Item -Force

    $manifestPath = Join-Path $packageRoot "PACKAGE_MANIFEST.sha256"
    $manifestLines = Get-ChildItem -LiteralPath $packageRoot -Recurse -File |
        Where-Object { $_.FullName -ne $manifestPath } |
        Sort-Object FullName |
        ForEach-Object {
            $relative = $_.FullName.Substring($packageRoot.Length + 1).Replace('\', '/')
            $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            "$hash  $relative"
        }
    [System.IO.File]::WriteAllLines($manifestPath, $manifestLines, [System.Text.UTF8Encoding]::new($false))

    Compress-Archive -LiteralPath $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal -Force
    $zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    [System.IO.File]::WriteAllText($hashPath, "$zipHash  $([System.IO.Path]::GetFileName($zipPath))`n", [System.Text.UTF8Encoding]::new($false))

    $roundTripRoot = Join-Path $stagingRoot "roundtrip"
    Expand-Archive -LiteralPath $zipPath -DestinationPath $roundTripRoot -Force
    $roundTripPackage = Join-Path $roundTripRoot "WirelessCityFactory"
    foreach ($required in @(
        "README.md",
        "docs\visualizer.md",
        "scripts\StartVisualizer.bat",
        "scripts\BuildAcceptancePackage.ps1",
        "src\wireless_city_factory\web_app.py",
        "tests\test_web_app.py",
        "unreal\WirelessCityFactory\WirelessCityFactory.uproject",
        "PACKAGE_MANIFEST.sha256"
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $roundTripPackage $required))) {
            throw "Round-trip validation failed; missing $required"
        }
    }

    Write-Host "Acceptance package: $zipPath"
    Write-Host "SHA-256 file: $hashPath"
    Write-Host "Package SHA-256: $zipHash"
} finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        $resolvedCleanup = [System.IO.Path]::GetFullPath($stagingRoot)
        if ($resolvedCleanup.StartsWith($resolvedOutputPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $stagingRoot -Recurse -Force
        }
    }
}
