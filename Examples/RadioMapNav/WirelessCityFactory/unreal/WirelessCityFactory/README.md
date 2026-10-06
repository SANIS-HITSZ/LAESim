# WirelessCityFactory Unreal Project

This is an independent Unreal Engine 4.27 C++ host project for the AirSim
1.8.1 plugin. The plugin is installed from an external AirSim checkout by
`scripts/SetupAirSim.ps1`; this project does not write back to that checkout.

## Build

```powershell
& .\Scripts\BuildProject.ps1
```

## Import the generated example city

Regenerate the UE bundle after changes to `wireless_city_factory`, then run:

```powershell
$RUN_DIR = "<RUN_DIR>"
& .\Scripts\ImportExampleCity.ps1 -BundleRoot $RUN_DIR -EngineRoot "<UE4_ROOT>"
```

The importer creates and saves a map under `/Game/WirelessCity/Maps`, imports
the city geometry with collision, assigns a neutral Engine default material,
adds base-station and mission markers, creates one AirSim `PlayerStart`, applies
`AirSimGameMode`, and adds one `DirectionalLight`, `SkyLight`, and
`SkyAtmosphere` for a visible daytime editor view. The native atmosphere is
used instead of the sunset-tinted `BP_Sky_Sphere`; the DirectionalLight is
pure white, has temperature disabled, intensity 10.0, and is placed at
Z=100000 cm for editor visibility.
Canonical right-handed +Z-up metre points are mapped to UE marker positions by
the current `scene_m_to_ue_cm=(x,-y,z)*100` contract, compensating for the
OBJ importer's Y inversion.

The import is idempotent. A completed `ue_import_result.json` with the same
scene fingerprint and the current visual import contract is reused without
spawning actors again. A completed marker with a different fingerprint or
contract is rebuilt or rejected so a hand-edited map is not silently
overwritten. Partial maps are cleaned only for generated actor labels.

Validate the saved map with an independent read-only UE Python pass:

```powershell
$RUN_DIR = "<RUN_DIR>"
& .\Scripts\ValidateExampleCity.ps1 -BundleRoot $RUN_DIR -EngineRoot "<UE4_ROOT>"
```

This writes `ue_validation_result.json` beside the bundle and checks map
loading, `AirSimGameMode`, one geometry actor with a non-empty material and
collision, the expected base-station and task marker counts, one `PlayerStart`,
and the three visual actors plus their key light properties. It also checks the
watertight geometry contract and satellite compatibility assets. Unreal command-line Python can
return process exit code 0 even when a script raises; the PowerShell wrapper
therefore requires the machine-readable marker to have `status: complete`.

Open `WirelessCityFactory.uproject` in UE 4.27 for visual inspection and Play-in-
Editor validation. Copy the generated bundle `settings.json` to
`%USERPROFILE%\Documents\AirSim\settings.json` before running AirSim.
