# City and base-station scenario profiles

> Radio contract v4 correction (2026-09-25): v3 passed sector angles to Sionna in the wrong Euler-angle order, so the three nominal azimuths shared the same effective boresight. Existing v3 radio volumes, feasibility runs, production-set files and convergence numbers below are retained as historical records but must be regenerated before they are used as validated physical results. City geometry and base-station coordinates are unaffected.

## Why profiles are used

A different random seed changes individual buildings, but it does not create a different class of city. A city profile changes the morphology and the distributions that control roads, footprints, coverage and height. Multiple seeds are then sampled inside each profile.

## City profiles

| Profile | Morphology | Intended distinction |
| --- | --- | --- |
| `dense_highrise_grid` | Manhattan | Orthogonal high-rise core, wide arterial streets and tall-building obstruction at UAV altitude |
| `irregular_midrise` | Offset-junction street network | Organic mid-rise district with connected streets, bends and varied directions |
| `compact_radial_lowrise` | Radial/ring | Very dense low-rise fabric organized around radial and ring roads |
| `sparse_suburban` | BSP/T-junction | Low-rise suburb with large blocks and extensive open space |

## Frozen city set v1

The first formal city set was frozen on 2026-09-10 with these three profiles:

| Profile | Role in the set | Seeds |
| --- | --- | --- |
| `dense_highrise_grid` | Dense, regular high-rise core | `20260821`, `20260822`, `20260823` |
| `irregular_midrise` | Irregular, medium-height urban district | `20260821`, `20260822`, `20260823` |
| `sparse_suburban` | Sparse, open low-rise suburb | `20260821`, `20260822`, `20260823` |

This yields nine reproducible cities. `compact_radial_lowrise` remains an extension profile because its much larger building count increases UE import and Sionna RT cost. The frozen selection fixes the profile names and seeds; base-station pairing, production radio-map heights and ray budget are separate decisions.

Generate the frozen set with:

```powershell
& .\scripts\generate_city_set_v1.ps1
```

The city-only configuration deliberately generates zero base stations. This prevents its former 10-site comparison placeholder from being mistaken for the production deployment; formal base stations are assigned by the scenario matrix below.

The generated candidate manifest aggregates building count, footprint coverage, mean height and free-space fraction over all seeds. These statistics, geometry validity and UE/Sionna importability are the selection evidence; profile names alone are not evidence.

Generate the 4 x 3 matrix with:

```powershell
$PYTHON = ".\.venv\Scripts\python.exe"
& $PYTHON -m wireless_city_factory generate-candidates `
  --config configs\city_diverse_1km.yaml `
  --city-profiles dense_highrise_grid irregular_midrise compact_radial_lowrise sparse_suburban `
  --seeds 20260821 20260822 20260823 `
  --project-root .
```

## Base-station profiles

The deployment profiles are calibration references, not claims about every commercial network. The scenario geometry is anchored to 3GPP TR 38.901, especially Table 7.2-1 and its calibration tables:

- Official specification: https://www.etsi.org/deliver/etsi_tr/138900_138999/138901/18.00.00_60/tr_138901v180000p.pdf
- `3gpp_uma_calibration_reference`: 25 m antenna height above ground, 500 m reference inter-site distance, three sectors, 49 dBm calibration power and an 8 x 8 dual-polarized array proxy.
- `3gpp_umi_street_canyon_calibration_reference`: 10 m antenna height above ground, 200 m reference inter-site distance, three sectors, 44 dBm calibration power and an 8 x 8 dual-polarized array proxy.
- `project_intermediate_not_a_standard_profile`: 10 sites/km2 sensitivity point. It is intentionally labelled as a project experiment rather than a 3GPP scenario.

The 1 km finite window cannot reproduce an infinite hexagonal deployment or exactly realize every reference inter-site distance. Therefore each manifest records both the reference distance and the actual generated coordinates. The configured 5 and 30 sites/km2 cases are finite-window approximations to sparse UMa-like and dense UMi-like deployments.

`height_m` must be interpreted through `height_reference`:

- `absolute_agl`: antenna height above ground level. Use this for 3GPP reference profiles.
- `mast_above_rooftop`: mast length added above the host roof. Use this only for explicitly rooftop-relative custom deployments.

The source locator, deployment profile, actual antenna height, reference inter-site distance and placement metadata are copied into `base_station_manifest.json`. This prevents a 25 m absolute reference height from silently becoming roof height plus 25 m.

## Frozen city/base-station matrix v1

`configs/scenario_matrix_v1.yaml` freezes the first experiment matrix:

| City profile | Base-station baseline | Interpretation |
| --- | --- | --- |
| `dense_highrise_grid` | UMi street-canyon reference | Dense 10 m AGL microcell deployment among high-rise streets |
| `irregular_midrise` | UMa reference | 25 m AGL macro coverage over a medium-height irregular district |
| `sparse_suburban` | UMa reference | Low-density macro baseline only; it is not labelled as a 3GPP RMa calibration scenario |

All three use the project carrier (`4.9 GHz`), bandwidth (`100 MHz`) and a `2 m` XY receiver grid. Measurement heights are frozen at `35/65/95/115 m`, covering the task altitude interval and allowing interpolation between adjacent layers.

The former v3 `production_v1` sampling benchmark used `16,777,216` samples per logical sector. Its convergence figures are invalidated by the v4 sector-orientation correction and are not current acceptance evidence. A new v4 benchmark against the same `67,108,864`-sample reference is required before the sampling budget is frozen again.

## What remains a project choice

The project carrier at 4.9 GHz, 100 MHz bandwidth and detection threshold are experiment settings. They are not implied by the UMa or UMi labels. City profiles, base-station pairings, measurement heights and the `production_v1` sampling budget are frozen in scenario matrix v1.

The former v3 full-scale feasibility and production generation completed numerically, but those radio volumes are now invalidated for physical use by the orientation correction. Their files are retained for provenance and must not be presented as v4 validated outputs.
