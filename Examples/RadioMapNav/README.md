# RadioMapNav

Generate a city and a Sionna RT radio map, compare geometric and
connectivity-aware routes, then execute the selected route in LAESim.
The source supplied in `WirelessCityFactory.zip` is extracted under
`WirelessCityFactory/`; the two Word documents are the original usage notes.

## Offline generation and planning

Run from `Examples/RadioMapNav/WirelessCityFactory` in PowerShell:

```powershell
py -3.10 -m venv .venv-sionna310
& .\.venv-sionna310\Scripts\python.exe -m pip install -e ".[dev,rt]" "sionna-rt==2.1.0"
& .\.venv-sionna310\Scripts\python.exe -m pytest
& .\.venv-sionna310\Scripts\python.exe -m wireless_city_factory generate --config configs\connectivity_usecase.yaml --project-root .
$run = Get-ChildItem examples\outputs -Directory -Filter 'connectivity_usecase-*' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
& .\.venv-sionna310\Scripts\python.exe scripts\plan_connectivity_aware_route.py --run-dir $run.FullName --output (Join-Path $run.FullName 'route_comparison.json') --mode both --flight-altitude-m 65 --minimum-sinr-db 0
```

Actual ray tracing requires a compatible NVIDIA GPU and CUDA/OptiX runtime.
The unit tests do not require UE or a GPU. Maps are generated offline;
navigation queries the stored map rather than running ray tracing every frame.
The route planner is deterministic, not a trained neural policy.

## LAESim flight

Build LAESim first using the root Windows build instructions. Then install
the built plugin into the independent demo host (adjust the engine path):

```powershell
& scripts\SetupAirSim.ps1 -AirSimRoot ..\..\..
& unreal\WirelessCityFactory\Scripts\BuildProject.ps1 -EngineRoot 'E:\epgame\UE_4.27'
& unreal\WirelessCityFactory\Scripts\ImportExampleCity.ps1 -BundleRoot $run.FullName -EngineRoot 'E:\epgame\UE_4.27'
py -3.10 -m venv .venv-airsim310
& .\.venv-airsim310\Scripts\python.exe -m pip install 'numpy==1.26.4' PyYAML msgpack-rpc-python 'opencv-contrib-python==4.10.0.84'
Push-Location ..\..\..\PythonClient
& ..\Examples\RadioMapNav\WirelessCityFactory\.venv-airsim310\Scripts\python.exe -m pip install --no-build-isolation -e .
Pop-Location
$env:PYTHONPATH = (Resolve-Path src).Path
```

Keep the old `%USERPROFILE%\Documents\AirSim\settings.json` before using the
generated `ue_bundle/settings.json`. The browser's LAESim import action makes
a timestamped backup automatically. Launch the generated
`/Game/WirelessCity/Maps/ConnectivityUseCase` map in the demo UE host and start
Play, then run:

```powershell
& .\.venv-airsim310\Scripts\python.exe scripts\run_laesim_connectivity_mission.py --run-dir $run.FullName --output (Join-Path $run.FullName 'mission.jsonl')
```

Use separate Python environments: the legacy AirSim RPC client and the modern
Sionna RT stack have different dependency requirements.

## Browser view

```powershell
$env:WCF_UE4_ROOT = 'E:\epgame\UE_4.27'
$env:WCF_VISUALIZER_OUTPUT = (Resolve-Path examples\outputs).Path
& .\.venv-sionna310\Scripts\python.exe -m wireless_city_factory.web_app --no-browser
```

Open the URL printed by the server (normally `http://127.0.0.1:8765/`).
See [verification](VERIFICATION.md) for the release acceptance results and
[planning details](WirelessCityFactory/docs/connectivity_aware_planning.md)
for the algorithm and assumptions. Generated maps, local environments and
UE build products are deliberately not committed.

`WirelessCityFactory/PACKAGE_MANIFEST.sha256` is the original ZIP's file
inventory, not a manifest of the LAESim Git tree. Python installation metadata
and compiled caches from that archive are not source files and are excluded.
