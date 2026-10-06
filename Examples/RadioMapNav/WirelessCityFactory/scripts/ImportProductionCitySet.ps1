param(
    [string]$EngineRoot = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BundleSetPath = Join-Path $RepoRoot "examples\outputs\production_ue_bundles_v1\production_ue_bundle_set_v1.json"
$ImportScript = Join-Path $RepoRoot "unreal\WirelessCityFactory\Scripts\ImportExampleCity.ps1"
$ValidationScript = Join-Path $RepoRoot "unreal\WirelessCityFactory\Scripts\ValidateExampleCity.ps1"

if (-not (Test-Path -LiteralPath $BundleSetPath)) {
    throw "Production UE bundle set was not found: $BundleSetPath"
}

$BundleSet = Get-Content -LiteralPath $BundleSetPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($BundleSet.status -ne "complete" -or $BundleSet.bundle_count -ne 9) {
    throw "Production UE bundle set is not complete."
}

$Results = @()
foreach ($Run in $BundleSet.runs) {
    & $ImportScript -BundleRoot $Run.bundle_root -EngineRoot $EngineRoot | Out-Null
    & $ValidationScript -BundleRoot $Run.bundle_root -EngineRoot $EngineRoot | Out-Null

    $ImportResult = Get-Content -LiteralPath (Join-Path $Run.bundle_root "ue_import_result.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    $ValidationResult = Get-Content -LiteralPath (Join-Path $Run.bundle_root "ue_validation_result.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($ImportResult.status -ne "complete" -or $ValidationResult.status -ne "complete") {
        throw "UE import or validation failed for $($Run.city_profile) seed=$($Run.seed)."
    }
    if ($ImportResult.map_path -ne $Run.expected_map_path -or $ValidationResult.map_path -ne $Run.expected_map_path) {
        throw "UE map path does not match the frozen bundle set for $($Run.city_profile) seed=$($Run.seed)."
    }
    $Results += [ordered]@{
        city_profile = $Run.city_profile
        seed = $Run.seed
        map_path = $ImportResult.map_path
        source_scene_fingerprint = $ImportResult.source_scene_fingerprint
        import_status = $ImportResult.status
        validation_status = $ValidationResult.status
        checks = $ValidationResult.checks
    }
    Write-Host "UE complete: $($Run.city_profile) seed=$($Run.seed) map=$($ImportResult.map_path)"
}

$Report = [ordered]@{
    schema_version = "wireless-city-production-ue-import-set-v1"
    status = "complete"
    import_count = $Results.Count
    runs = $Results
}
$Output = Join-Path (Split-Path -Parent $BundleSetPath) "production_ue_import_set_v1.json"
$Temporary = "$Output.tmp"
$Report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Temporary -Encoding UTF8
Move-Item -LiteralPath $Temporary -Destination $Output -Force
$Report | ConvertTo-Json -Depth 12
