import json
from dataclasses import replace
from pathlib import Path

import pytest
from laesim_radio import build
from laesim_scene.config import config_from_mapping
from laesim_scene.pipeline import generate


def source_scene(tmp_path):
    config = config_from_mapping({"global": {"seed": 4, "name": "test", "output": str(tmp_path / "scenes")}, "city": {"size_m": [120, 120], "building": {"coverage_ratio": 0.08, "density_per_km2": 20}, "task": {"altitude_m": 50, "altitude_range_m": [35, 65]}}})
    result = generate(config)
    return Path(result["output_dir"]), replace(config, radio=replace(config.radio, enabled=True))


def test_radio_build_preserves_source_and_geometry(tmp_path, monkeypatch):
    source, config = source_scene(tmp_path)
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    def calculate(scene, radio, target, stations):
        (target / "radio_manifest.json").write_text('{"status":"complete"}')
        return {"radio_fingerprint": "new-radio"}
    monkeypatch.setattr(build, "run_radio_stage", calculate)
    output = tmp_path / "radio"
    result = build.build_radio_map(source, config, output)
    assert result["stage_status"]["radio"]["radio_fingerprint"] == "new-radio"
    assert result["stage_status"]["ue"]["status"] == "disabled"
    assert (output / "scene.obj").read_bytes() == before["scene.obj"]
    assert {p.name: p.read_bytes() for p in source.iterdir()} == before
    assert json.loads((output / "manifest.json").read_text())["status"] == "complete"
    with pytest.raises(ValueError, match="new output"):
        build.build_radio_map(source, config, output)


def test_radio_failure_publishes_nothing(tmp_path, monkeypatch):
    source, config = source_scene(tmp_path)
    def fail(*args):
        raise RuntimeError("solver failed")
    monkeypatch.setattr(build, "run_radio_stage", fail)
    with pytest.raises(RuntimeError, match="solver failed"):
        build.build_radio_map(source, config, tmp_path / "radio")
    assert not (tmp_path / "radio").exists()
    assert not list(tmp_path.glob(".laesim-radio-*"))


def test_radio_build_rejects_different_geometry(tmp_path):
    source, config = source_scene(tmp_path)
    with pytest.raises(ValueError, match="City parameters"):
        build.build_radio_map(source, replace(config, seed=config.seed + 1), tmp_path / "radio")
    with pytest.raises(ValueError, match="outside"):
        build.build_radio_map(source, config, source / "radio")
