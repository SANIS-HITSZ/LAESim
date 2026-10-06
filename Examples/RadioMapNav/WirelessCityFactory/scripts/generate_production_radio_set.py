"""Generate the frozen production_v1 radio-map matrix sequentially."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from wireless_city_factory.config import FactoryConfig, config_from_mapping, load_config
from wireless_city_factory.pipeline import generate
from wireless_city_factory.profiles import apply_city_profile

REUSED_FEASIBILITY_NAMES = {
    ("dense_highrise_grid", 20260821): "feasibility_dense_highrise_umi_1km_2m",
    ("irregular_midrise", 20260821): "feasibility_irregular_midrise_uma_1km_2m",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    return parser.parse_args()


def _build_config(
    city_base: FactoryConfig,
    city_profile: str,
    seed: int,
    station_source: FactoryConfig,
) -> FactoryConfig:
    profiled = apply_city_profile(city_base, city_profile)
    radio = config_from_mapping(
        {
            "radio": {
                "enabled": True,
                "preset": "production_v1",
                "tx_power_dbm": station_source.city.base_stations.power_dbm,
                "downtilt_deg": station_source.city.base_stations.downtilt_deg,
                "seed": seed,
            }
        }
    ).radio
    name = REUSED_FEASIBILITY_NAMES.get(
        (city_profile, seed),
        f"production_v1-{city_profile}-seed-{seed}",
    )
    return replace(
        profiled,
        seed=seed,
        name=name,
        city=replace(
            profiled.city,
            base_stations=station_source.city.base_stations,
            task=replace(profiled.city.task, altitude_m=65.0),
        ),
        radio=radio,
        ue=replace(profiled.ue, enabled=False),
    )


def main() -> int:
    args = _parse_args()
    project_root = args.project_root.resolve()
    matrix = yaml.safe_load(args.matrix.read_text(encoding="utf-8"))
    if matrix.get("status") != "production_parameters_frozen":
        raise ValueError("scenario matrix is not frozen for production")

    city_base = load_config(project_root / "configs" / "city_set_v1.yaml")
    station_profiles = {
        key: load_config(project_root / value["config"])
        for key, value in matrix["base_station_profiles"].items()
    }
    pairing_by_city = {
        item["city_profile"]: item["base_station_profile"] for item in matrix["pairings"]
    }

    runs: list[dict[str, Any]] = []
    for city_profile in matrix["city_set"]["profiles"]:
        station_profile = pairing_by_city[city_profile]
        for seed in matrix["city_set"]["seeds"]:
            config = _build_config(
                city_base,
                city_profile,
                int(seed),
                station_profiles[station_profile],
            )
            result = generate(config, project_root=project_root)
            run_dir = Path(result["output_dir"])
            radio_manifest = json.loads(
                (run_dir / "radio_manifest.json").read_text(encoding="utf-8")
            )
            runs.append(
                {
                    "city_profile": city_profile,
                    "seed": int(seed),
                    "base_station_profile": station_profile,
                    "run_id": result["run_id"],
                    "output_dir": str(run_dir),
                    "reused": bool(result.get("reused", False)),
                    "scene_fingerprint": result["scene_fingerprint"],
                    "radio_fingerprint": radio_manifest["radio_fingerprint"],
                    "shape": radio_manifest["shape"],
                    "transmitter_count": len(radio_manifest["transmitter_ids"]),
                    "solver_elapsed_s": radio_manifest.get("runtime", {}).get("solver_elapsed_s"),
                }
            )
            print(f"complete: {city_profile} seed={seed} run={result['run_id']}", flush=True)

    report = {
        "schema_version": "wireless-city-production-radio-set-v1",
        "status": "complete",
        "matrix": str(args.matrix),
        "run_count": len(runs),
        "runs": runs,
    }
    output = project_root / "examples" / "outputs" / "production_radio_set_v1.json"
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({**report, "report": str(output)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
