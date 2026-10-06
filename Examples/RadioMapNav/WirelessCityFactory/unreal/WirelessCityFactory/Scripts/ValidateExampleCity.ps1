param(
    [Parameter(Mandatory = $true)]
    [string]$BundleRoot,
    [string]$EngineRoot = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectFile = Join-Path $projectRoot "WirelessCityFactory.uproject"
$bundle = (Resolve-Path -LiteralPath $BundleRoot).Path
$validator = Join-Path $projectRoot "Scripts\ValidateImportedCity.py"

if (-not $EngineRoot) {
    $launcherManifest = "C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat"
    if (Test-Path -LiteralPath $launcherManifest) {
        $launcher = Get-Content -LiteralPath $launcherManifest -Raw | ConvertFrom-Json
        $entry = $launcher.InstallationList | Where-Object { $_.AppName -eq "UE_4.27" } | Select-Object -First 1
        if ($entry) { $EngineRoot = $entry.InstallLocation }
    }
}

$editor = Join-Path $EngineRoot "Engine\Binaries\Win64\UE4Editor-Cmd.exe"
if (-not (Test-Path -LiteralPath $editor)) {
    throw "UE4Editor-Cmd was not found: $editor"
}

$output = Join-Path $bundle "ue_validation_result.json"
$savedBundle = $env:WCF_BUNDLE_ROOT
$savedOutput = $env:WCF_VALIDATION_OUTPUT
try {
    $env:WCF_BUNDLE_ROOT = $bundle
    $env:WCF_VALIDATION_OUTPUT = $output
    & $editor $projectFile "-ExecutePythonScript=$validator" -unattended -nop4 -nosplash -NoSound -NullRHI -stdout -FullStdOutLogOutput
    if ($LASTEXITCODE -ne 0) {
        throw "UE validation process failed with exit code $LASTEXITCODE"
    }
}
finally {
    if ($null -eq $savedBundle) { Remove-Item Env:WCF_BUNDLE_ROOT -ErrorAction SilentlyContinue } else { $env:WCF_BUNDLE_ROOT = $savedBundle }
    if ($null -eq $savedOutput) { Remove-Item Env:WCF_VALIDATION_OUTPUT -ErrorAction SilentlyContinue } else { $env:WCF_VALIDATION_OUTPUT = $savedOutput }
}

if (-not (Test-Path -LiteralPath $output)) {
    throw "UE validation exited without producing $output"
}
$result = Get-Content -LiteralPath $output -Raw | ConvertFrom-Json
if ($result.status -ne "complete") {
    throw ("UE validation failed: " + ($result | ConvertTo-Json -Depth 8 -Compress))
}
Get-Content -LiteralPath $output -Raw
