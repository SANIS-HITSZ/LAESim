param(
    [string]$Config = "",
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $Config) { $Config = Join-Path $RepoRoot "SceneGen\configs\city_only.yaml" }
if (-not $Python) { $Python = Join-Path $RepoRoot ".venv-radio\Scripts\python.exe" }
& $Python -m laesim_scene generate --config $Config --project-root $RepoRoot
if ($LASTEXITCODE -ne 0) { throw "Scene generation failed." }
