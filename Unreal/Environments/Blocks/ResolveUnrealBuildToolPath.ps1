param(
    [string]$ProjectDir = (Get-Location).Path
)

$ErrorActionPreference = "SilentlyContinue"

$uproject = Get-ChildItem -LiteralPath $ProjectDir -Filter *.uproject | Select-Object -First 1
$engineAssoc = ""

if ($uproject) {
    try {
        $engineAssoc = [string]((Get-Content -Raw -LiteralPath $uproject.FullName | ConvertFrom-Json).EngineAssociation)
    }
    catch {
        $engineAssoc = ""
    }
}

$roots = New-Object System.Collections.Generic.List[string]

foreach ($name in "UNREAL_ENGINE_ROOT", "UE_ROOT", "UE4_ROOT") {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ($value) {
        $roots.Add($value)
    }
}

if ($engineAssoc) {
    $reg = Get-ItemProperty "HKCU:\Software\Epic Games\Unreal Engine\Builds" -ErrorAction SilentlyContinue
    if ($reg) {
        $prop = $reg.PSObject.Properties[$engineAssoc]
        if ($prop) {
            $roots.Add([string]$prop.Value)
        }
    }
}

if ($engineAssoc) {
    foreach ($base in @(
        [Environment]::GetEnvironmentVariable("ProgramW6432"),
        [Environment]::GetEnvironmentVariable("ProgramFiles(x86)"),
        [Environment]::GetEnvironmentVariable("ProgramFiles")
    )) {
        if ($base) {
            $roots.Add((Join-Path $base ("Epic Games\UE_" + $engineAssoc)))
        }
    }
}

if ($engineAssoc) {
    foreach ($drive in (Get-PSDrive -PSProvider FileSystem | Select-Object -ExpandProperty Root)) {
        if ($drive) {
            $roots.Add((Join-Path $drive ("Epic Games\UE_" + $engineAssoc)))
            $roots.Add((Join-Path $drive ("Epic\UE_" + $engineAssoc)))
            $roots.Add((Join-Path $drive ("Epic\UE\UE_" + $engineAssoc)))
        }
    }
}

$seen = @{}
foreach ($root in $roots) {
    if (-not $root -or $seen.ContainsKey($root)) {
        continue
    }

    $seen[$root] = $true
    $ubt = Join-Path $root "Engine\Binaries\DotNET\UnrealBuildTool.exe"
    if (Test-Path $ubt) {
        Write-Output $ubt
        exit 0
    }
}

exit 1
