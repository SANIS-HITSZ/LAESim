param(
    [string]$LAESimRoot = "",
    [string]$ProjectRoot = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $LAESimRoot) { $LAESimRoot = $repositoryRoot }
$LAESimRoot = (Resolve-Path -LiteralPath $LAESimRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $LAESimRoot "PythonClient\airsim\client.py")) -or
    -not (Test-Path -LiteralPath (Join-Path $LAESimRoot "AirLib\include"))) {
    throw "This host requires a LAESim checkout, not a standalone AirSim distribution."
}
$AirSimRoot = $LAESimRoot

if (-not $ProjectRoot) {
    $ProjectRoot = Join-Path $repositoryRoot "Unreal\Environments\SceneGen"
}

$AirSimRoot = (Resolve-Path -LiteralPath $AirSimRoot).Path
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path

$pluginCandidates = @(
    (Join-Path $AirSimRoot "Unreal\Plugins\AirSim"),
    (Join-Path $AirSimRoot "Unreal\Environments\Blocks\Plugins\AirSim")
)
$pluginSource = $pluginCandidates |
    Where-Object { Test-Path -LiteralPath (Join-Path $_ "AirSim.uplugin") } |
    Select-Object -First 1
if (-not $pluginSource) {
    throw "AirSim.uplugin was not found below AirSimRoot. Expected an Unreal plugin directory."
}

$pluginDestination = Join-Path $ProjectRoot "Plugins\AirSim"
if ((Test-Path -LiteralPath $pluginDestination) -and -not $Force) {
    throw "Project AirSim plugin already exists: $pluginDestination. Use -Force only when merging/updating it."
}
New-Item -ItemType Directory -Path $pluginDestination -Force | Out-Null
Copy-Item -Path (Join-Path $pluginSource "*") -Destination $pluginDestination -Recurse -Force

$satelliteCandidates = @(
    (Join-Path $AirSimRoot "Unreal\Assets\Satellite\Models\Satellite"),
    (Join-Path $AirSimRoot "Unreal\Environments\Blocks\Content\AirSim\Models\Satellite"),
    (Join-Path $AirSimRoot "Unreal\Plugins\AirSim\Content\Models\Satellite")
)
$satelliteSource = $satelliteCandidates |
    Where-Object {
        (Test-Path -LiteralPath (Join-Path $_ "10477_Satellite_v1.uasset")) -and
        (Test-Path -LiteralPath (Join-Path $_ "10477_Satellite_v1_L3.uasset"))
    } |
    Select-Object -First 1
if (-not $satelliteSource) {
    throw "Required 10477_Satellite_v1 and L3 compatibility assets were not found below AirSimRoot."
}

$satelliteDestination = Join-Path $ProjectRoot "Content\AirSim\Models\Satellite"
New-Item -ItemType Directory -Path $satelliteDestination -Force | Out-Null
Copy-Item -Path (Join-Path $satelliteSource "*") -Destination $satelliteDestination -Recurse -Force

$files = @(
    Get-ChildItem -LiteralPath $satelliteDestination -File |
        Sort-Object Name |
        ForEach-Object {
            [ordered]@{
                file = $_.Name
                sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
            }
        }
)
$compatibilityManifest = [ordered]@{
    status = "copied-real-assets"
    source = $satelliteSource
    destination = "/Game/AirSim/Models/Satellite"
    laesim_modified = $false
    files = $files
}
$manifestPath = Join-Path $satelliteDestination "compat_manifest.json"
$compatibilityManifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host "AirSim plugin copied from: $pluginSource"
Write-Host "AirSim plugin installed at: $pluginDestination"
Write-Host "Satellite compatibility assets copied from: $satelliteSource"
Write-Host "Satellite compatibility manifest: $manifestPath"
