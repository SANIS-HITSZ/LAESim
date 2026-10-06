"""Publish a new radio snapshot without modifying its source scene."""

import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

from laesim_scene.config import FactoryConfig, config_from_mapping
from laesim_scene.schema import load_scene

from .base_stations import load_base_station_manifest
from .radio import run_radio_stage


def build_radio_map(scene_run: Path, config: FactoryConfig, output: Path) -> dict:
    scene_run, output = scene_run.resolve(), output.resolve()
    if output.exists() or scene_run in output.parents:
        raise ValueError("Use a new output directory outside the source scene run.")
    if not config.radio.enabled:
        raise ValueError("Radio calculation must be enabled in the configuration.")
    source = json.loads((scene_run / "manifest.json").read_text(encoding="utf-8"))
    original = config_from_mapping(json.loads((scene_run / "config.json").read_text(encoding="utf-8")))
    if source.get("status") != "complete" or source.get("config_fingerprint") != original.fingerprint():
        raise ValueError("Source scene run is incomplete or its configuration fingerprint differs.")
    if config.city != original.city or config.seed != original.seed:
        raise ValueError("City parameters and seed must match the source scene; only radio settings may change.")
    scene = load_scene(scene_run / "scene.json")
    if scene.fingerprint() != source.get("scene_fingerprint"):
        raise ValueError("Source scene fingerprint differs from its manifest.")
    stations = load_base_station_manifest(scene_run / "base_station_manifest.json", scene)
    derived = replace(original, radio=config.radio, ue=replace(original.ue, enabled=False), output=str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".laesim-radio-", dir=output.parent) as temporary:
        staging = Path(temporary)
        for name in ("scene.json", "scene.obj", "preview.svg", "city_manifest.json", "base_station_manifest.json"):
            shutil.copy2(scene_run / name, staging / name)
        radio = run_radio_stage(scene, derived.radio, staging, stations)
        manifest = {
            "status": "complete", "run_id": output.name,
            "config_fingerprint": derived.fingerprint(),
            "scene_fingerprint": scene.fingerprint(), "scene_file": "scene.json",
            "source_scene_run": str(scene_run),
            "stage_status": {
                "city": source["stage_status"]["city"],
                "radio": {"status": "complete", "manifest": "radio_manifest.json", "radio_fingerprint": radio["radio_fingerprint"]},
                "ue": {"status": "disabled"},
            },
        }
        (staging / "config.json").write_text(json.dumps(derived.as_dict(), indent=2), encoding="utf-8")
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
        # The lookup's radio manifest is published atomically after every volume file.
        output.mkdir()
        try:
            for file in staging.iterdir():
                if file.name not in {"manifest.json", "radio_manifest.json"}:
                    shutil.copy2(file, output / file.name)
            shutil.copy2(staging / "manifest.json", output / "manifest.json")
            radio_marker = output / ".radio_manifest.json.tmp"
            shutil.copy2(staging / "radio_manifest.json", radio_marker)
            radio_marker.replace(output / "radio_manifest.json")
        except Exception:
            shutil.rmtree(output)
            raise
    return {**manifest, "output_dir": str(output)}
