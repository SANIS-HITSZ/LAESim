param(
    [string]$EngineRoot = "",
    [string]$ProjectFile = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $ProjectFile) { $ProjectFile = Join-Path $repositoryRoot "Unreal\Environments\SceneGen\WirelessCityFactory.uproject" }
$projectFile = (Resolve-Path -LiteralPath $ProjectFile).Path
$projectRoot = Split-Path -Parent $projectFile

if (-not $EngineRoot) {
    $launcherManifest = "C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat"
    if (Test-Path -LiteralPath $launcherManifest) {
        $launcher = Get-Content -LiteralPath $launcherManifest -Raw | ConvertFrom-Json
        $entry = $launcher.InstallationList | Where-Object { $_.AppName -eq "UE_4.27" } | Select-Object -First 1
        if ($entry) {
            $EngineRoot = $entry.InstallLocation
        }
    }
}

if (-not $EngineRoot) {
    throw "UE 4.27 was not found. Pass -EngineRoot explicitly."
}

$ubt = Join-Path $EngineRoot "Engine\Binaries\DotNET\UnrealBuildTool.exe"
if (-not (Test-Path -LiteralPath $ubt)) {
    throw "UnrealBuildTool was not found: $ubt"
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "Plugins\AirSim\AirSim.uplugin"))) {
    throw "The project-local AirSim plugin is missing."
}

& $ubt -projectfiles -project="$projectFile" -game -rocket -progress
if ($LASTEXITCODE -ne 0) {
    throw "Visual Studio project generation failed with exit code $LASTEXITCODE"
}

& $ubt WirelessCityFactoryEditor Win64 Development -Project="$projectFile" -WaitMutex -FromMsBuild
if ($LASTEXITCODE -ne 0) {
    throw "Unreal project build failed with exit code $LASTEXITCODE"
}

Write-Host "Built WirelessCityFactoryEditor successfully."
