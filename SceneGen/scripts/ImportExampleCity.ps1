param(
    [Parameter(Mandatory = $true)]
    [string]$BundleRoot,
    [string]$EngineRoot = "",
    [string]$ProjectFile = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $ProjectFile) { $ProjectFile = Join-Path $repositoryRoot "Unreal\Environments\SceneGen\WirelessCityFactory.uproject" }
$projectFile = (Resolve-Path -LiteralPath $ProjectFile).Path
$BundleRoot = (Resolve-Path -LiteralPath $BundleRoot).Path
$importer = Join-Path $BundleRoot "ue_bundle\import_wireless_city.py"

if (-not (Test-Path -LiteralPath $importer)) {
    throw "UE importer was not found: $importer"
}

if (-not $EngineRoot) {
    $launcherManifest = "C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat"
    $launcher = Get-Content -LiteralPath $launcherManifest -Raw | ConvertFrom-Json
    $entry = $launcher.InstallationList | Where-Object { $_.AppName -eq "UE_4.27" } | Select-Object -First 1
    if ($entry) {
        $EngineRoot = $entry.InstallLocation
    }
}

$editor = Join-Path $EngineRoot "Engine\Binaries\Win64\UE4Editor-Cmd.exe"
if (-not (Test-Path -LiteralPath $editor)) {
    throw "UE4Editor-Cmd was not found: $editor"
}

& $editor $projectFile "-ExecutePythonScript=$importer" -unattended -nop4 -nosplash -NoSound -NullRHI -stdout -FullStdOutLogOutput
if ($LASTEXITCODE -ne 0) {
    throw "UE import failed with exit code $LASTEXITCODE"
}

$result = Join-Path $BundleRoot "ue_import_result.json"
if (-not (Test-Path -LiteralPath $result)) {
    throw "The importer exited without producing $result"
}
$marker = Get-Content -LiteralPath $result -Raw | ConvertFrom-Json
if ($marker.status -ne "complete" -or $marker.import_contract -ne "wireless-city-ue-import-visual" -or $marker.geometry_contract -ne "wireless-city-obj-watertight" -or $marker.coordinate_contract -ne "wireless-city-scene-to-ue-cm-yflip" -or $marker.coordinate_transform -ne "scene_m_to_ue_cm=(x,-y,z)*100" -or -not $marker.source_scene_fingerprint -or -not $marker.actor_counts -or -not $marker.visual_actor_counts -or -not $marker.visual_settings -or -not $marker.geometry_material) {
    throw ("UE importer did not publish a complete machine-readable marker: " + ($marker | ConvertTo-Json -Depth 8 -Compress))
}

$validatorScript = Join-Path $PSScriptRoot "ValidateExampleCity.ps1"
& $validatorScript -BundleRoot $BundleRoot -EngineRoot $EngineRoot -ProjectFile $projectFile | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "UE validation failed after import"
}
Get-Content -LiteralPath $result -Raw
