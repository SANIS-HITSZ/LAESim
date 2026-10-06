"""Create unique Unreal import bundles from the frozen production radio set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from laesim_radio.base_stations import load_base_station_manifest
from laesim_scene.config import UEConfig
from laesim_scene.schema import load_scene
from laesim_scene.ue import generate_ue_bundle, validate_ue_bundle

ASSET_PREFIX = {
    "dense_highrise_grid": "WCF_DenseHighriseGrid",
    "irregular_midrise": "WCF_IrregularMidrise",
    "sparse_suburban": "WCF_SparseSuburban",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--radio-set", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    project_root = args.project_root.resolve()
    radio_set = json.loads(args.radio_set.read_text(encoding="utf-8"))
    if radio_set.get("status") != "complete" or radio_set.get("run_count") != 9:
        raise ValueError("production radio set must contain nine completed runs")

    output_root = project_root / "SceneGen" / "outputs" / "production_ue_bundles_v1"
    output_root.mkdir(parents=True, exist_ok=True)
    runs = []
    for source in radio_set["runs"]:
        profile = source["city_profile"]
        seed = int(source["seed"])
        source_dir = Path(source["output_dir"])
        scene = load_scene(source_dir / "scene.json")
        stations = load_base_station_manifest(source_dir / "base_station_manifest.json", scene)
        asset_name = f"{ASSET_PREFIX[profile]}_{seed}"
        bundle_root = output_root / f"{profile}-seed-{seed}"
        config = UEConfig(
            enabled=True,
            editor_project="Unreal/Environments/SceneGen/WirelessCityFactory.uproject",
            generate_airsim_settings=True,
            import_asset_name=asset_name,
            marker_scale_m=2.0,
        )
        scene.save_json(bundle_root / "scene.json")
        manifest = generate_ue_bundle(scene, config, bundle_root, stations)
        validate_ue_bundle(bundle_root)
        runs.append(
            {
                "city_profile": profile,
                "seed": seed,
                "asset_name": asset_name,
                "expected_map_path": f"/Game/WirelessCity/Maps/{asset_name}",
                "bundle_root": str(bundle_root),
                "source_radio_run_id": source["run_id"],
                "source_scene_fingerprint": manifest["source_scene_fingerprint"],
                "base_station_fingerprint": manifest["base_station_fingerprint"],
                "bundle_status": manifest["status"],
            }
        )
        print(f"bundle complete: {profile} seed={seed}", flush=True)

    report = {
        "schema_version": "wireless-city-production-ue-bundle-set-v1",
        "status": "complete",
        "bundle_count": len(runs),
        "source_radio_set": str(args.radio_set),
        "runs": runs,
    }
    output = output_root / "production_ue_bundle_set_v1.json"
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({**report, "report": str(output)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
