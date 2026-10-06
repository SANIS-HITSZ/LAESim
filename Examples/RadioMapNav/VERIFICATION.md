# V1.6 RadioMapNav Acceptance

Verified locally on 2026-10-06. These results are from a new execution of the
extracted demo, not copied from the original Word documents.

## Environment and configuration

- Windows; Python 3.10.11; NVIDIA RTX 3090 (24 GB), driver 610.88.
- Sionna RT 2.1.0, Mitsuba 3.9.1, Dr.Jit 1.5.0, NumPy 2.2.6.
- Separate AirSim client environment: NumPy 1.26.4, msgpack-rpc-python 0.4.1,
  Tornado 4.5.3, OpenCV contrib 4.10.0.84, current LAESim PythonClient 1.8.1.
- AirLib Release rebuilt from current LAESim source with VS 2019; demo host
  and the current LAESim plugin rebuilt with UE 4.27.
- `WirelessCityFactory/configs/connectivity_usecase.yaml`, seed 20260824:
  400 x 400 m Manhattan city, 63 buildings, 4 sites / 12 sectors, 3.5 GHz,
  100 MHz, 38 dBm per sector, 8 x 8 cross-polarized array.
- Radio map: 65 m height, 20 m cells, tensor shape `[12, 1, 20, 20]`,
  16,384 samples per sector, maximum ray depth 6, CUDA polarized backend.
- Mission: start `(50, 50, 65)` m, goal `(350, 330, 65)` m,
  minimum SINR 0 dB, cruise speed 5 m/s, sampling period 0.25 s.

## Results

| Stage | Result |
| --- | --- |
| Inherited V1.5 portable verification | PASS; 33 deterministic tests and direct backend smoke test |
| RadioMapNav CPU tests | 105 passed (including completed-result retention) |
| Real Sionna RT map generation | PASS; CUDA computation, not a mock map |
| Offline baseline and connectivity planning | Both reached the goal |
| Current AirLib and UE demo compilation | PASS |
| UE scene import and validator | PASS; all 22 checks true |
| Actual LAESim mission | Exit code 0; completion record written |
| Desktop / mobile browser | 1440 x 900 and 390 x 844; nonblank WebGL canvas, no page errors or horizontal overflow |

Offline command-line comparison (both routes are planned, not both flown):

| Metric | Geometry baseline | Connectivity-aware |
| --- | --- | --- |
| Length | 411.029 m | 476.533 m |
| Outage fraction | 7.960% | 0% |
| Minimum SINR | -3.229 dB | 0.037 dB |
| Mean SINR | 10.390 dB | 12.520 dB |
| Handovers | 5 | 2 |
| Replans | 39 | 4 |

Actual UE connectivity-aware flight:

- 378 sampled flight states; no collision and no outage samples.
- Sampled trajectory length 476.698 m; final goal error 0.444 m.
- Actual sampled altitude 65.193 to 66.542 m. Wireless queries use the XY
  position projected to the fixed 65 m map layer; they do not recompute the
  channel at the instantaneous flight height.
- Launch-time ground contact is not counted as an en-route collision; all
  recorded flight samples have `has_collided=false`.
- The live mission replans from the measured starting pose, so its baseline
  metrics differ slightly from the exact-coordinate offline comparison.
- Refreshing the browser now restores the current mission instead of first
  generating an unrelated default city. Fingerprint mismatch rejection remains.
- Completed results remain available after the live-state timeout; restoring
  a mission also restores its radio-layer switch so the heatmap can be displayed.

The original source includes a paper-evidence exporter. Compact outputs from
this execution are stored in `verification/2026-10-06/`; the full map and flight
log remain local in the ignored generated-output and runtime directories.

## Fingerprints

```text
run_id: connectivity_usecase-9608b3f43650
config: 9608b3f43650568215ad3f4cd396bd8008c785a3f7435ce450f02cdbf02c016b
scene: e639364a256f6c86bce3702268e50ac190bcfd54347f4cfc2ac57fa6c7f79a78
stations: 911e02b42f662d25e911ea7ba7abd9a6e2b11451cea95eca655d9b6b38b1fbb0
radio: 57f730c8f5c0c01f8b6d29e7b72a06ee0b1bf76f6700ee8ace72b4f857325c87
```

## Boundaries

This is a static, site-specific propagation map with runtime interpolation,
not online per-frame ray tracing, trained neural navigation, or packet-level
network simulation. The existing ns-3 integration is unchanged and was not
rerun as part of this demo acceptance. A fixed configuration succeeded; other
cities, heights or thresholds may correctly report an infeasible route.

The LLVM initialization warning did not prevent the selected CUDA backend
from generating the map. UE reported nonfatal default-material and weather
blueprint warnings; scene material, geometry collision and visual settings
passed the import validator, and the mission completed.
