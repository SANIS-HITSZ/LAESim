param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = Join-Path $RepoRoot ".venv-radio\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python environment not found at '$Python'. Pass -Python with the project Python path."
}

& $Python -m laesim_scene generate-candidates `
    --config (Join-Path $RepoRoot "SceneGen\configs\city_set_v1.yaml") `
    --city-profiles dense_highrise_grid irregular_midrise sparse_suburban `
    --seeds 20260821 20260822 20260823 `
    --project-root $RepoRoot

if ($LASTEXITCODE -ne 0) {
    throw "City set v1 generation failed with exit code $LASTEXITCODE."
}
