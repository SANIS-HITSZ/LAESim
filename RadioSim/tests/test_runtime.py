import json

import numpy as np
import pytest
from laesim_radio.runtime import PositionOutOfBoundsError, RadioMapLookup
from laesim_scene.city import generate_city
from laesim_scene.config import config_from_mapping


def _lookup() -> RadioMapLookup:
    config = config_from_mapping({
        "global": {"seed": 7},
        "city": {
            "size_m": [100, 100],
            "building": {"coverage_ratio": 0.05, "density_per_km2": 10},
            "task": {"altitude_m": 50, "altitude_range_m": [35, 65]},
        },
    })
    scene = generate_city(config.city, seed=config.seed)
    station_id = str(scene.base_stations[0]["base_station_id"])
    values = np.array([
        [
            [[1e-12, 2e-12], [3e-12, 4e-12]],
            [[5e-12, 6e-12], [7e-12, 8e-12]],
        ],
        np.full((2, 2, 2), 1e-14),
    ])
    metadata = {
        "antenna_model": "isotropic",
        "transmitter_ids": [station_id, station_id + "-sector-00"],
        "config": {
            "tx_power_dbm": 44.0,
            "frequency_hz": 4.9e9,
            "bandwidth_hz": 20e6,
            "temperature_k": 293.0,
            "noise_figure_db": 9.0,
            "sector_azimuths_deg": [0.0],
            "downtilt_deg": 0.0,
        },
    }
    return RadioMapLookup(
        scene,
        (station_id, station_id + "-sector-00"),
        np.array([25.0, 75.0]),
        np.array([25.0, 75.0]),
        np.array([35.0, 65.0]),
        values,
        metadata,
    )


def test_runtime_query_interpolates_and_filters_metadata() -> None:
    lookup = _lookup()
    observation = lookup.query((50.0, 50.0, 50.0), detection_threshold_dbm=-90.0)
    expected_gain = 4.5e-12
    assert observation.rss_dbm == {
        lookup.transmitter_ids[0]: pytest.approx(44.0 + 10.0 * np.log10(expected_gain))
    }
    assert observation.serving_cell == lookup.transmitter_ids[0]
    assert len(observation.detected_cells) == 1
    assert observation.detected_cells[0]["site_id"] == lookup.transmitter_ids[0]
    assert observation.sinr_db is not None and np.isfinite(observation.sinr_db)
    assert json.loads(json.dumps(observation.to_dict()))["interpolation"] == "trilinear-linear-path-gain"
    assert observation.to_dict()["rsrp_dbm"] == observation.to_dict()["rss_dbm"]


def test_runtime_converts_airsim_ned_to_canonical_scene() -> None:
    lookup = _lookup()
    start = lookup.scene.tasks[0]["start_m"]
    converted = lookup.canonical_from_airsim_ned((2.0, 3.0, -4.0))
    assert converted == pytest.approx((start[0] + 2.0, start[1] - 3.0, start[2] + 4.0))


def test_runtime_converts_canonical_scene_to_airsim_ned() -> None:
    lookup = _lookup()
    start = lookup.scene.tasks[0]["start_m"]
    converted = lookup.airsim_ned_from_canonical(
        (start[0] + 2.0, start[1] - 3.0, start[2] + 4.0)
    )
    assert converted == pytest.approx((2.0, 3.0, -4.0))


def test_runtime_returns_no_cell_when_detection_threshold_is_not_met() -> None:
    observation = _lookup().query((50.0, 50.0, 50.0), detection_threshold_dbm=100.0)
    assert observation.detected_cells == []
    assert observation.rss_dbm == {}
    assert observation.serving_cell is None
    assert observation.sinr_db is None
    assert observation.outage is True


def test_runtime_rejects_out_of_bounds_instead_of_clamping() -> None:
    lookup = _lookup()
    lookup.query((-1e-5, 50.0, 50.0))
    with pytest.raises(PositionOutOfBoundsError):
        lookup.query((-0.1, 50.0, 50.0))
    with pytest.raises(PositionOutOfBoundsError):
        lookup.query((50.0, 50.0, 70.0))
