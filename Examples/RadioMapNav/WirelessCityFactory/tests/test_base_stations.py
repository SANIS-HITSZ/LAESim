import copy

import pytest

from wireless_city_factory.base_stations import (
    build_base_station_manifest,
    load_base_station_manifest,
    save_base_station_manifest,
    validate_base_station_manifest,
)
from wireless_city_factory.city import generate_city
from wireless_city_factory.config import config_from_mapping, load_config
from wireless_city_factory.radio import _validate_radio_station_contract


def _config(*, radio_power_dbm: float = 44.0):
    return config_from_mapping(
        {
            "global": {"seed": 31},
            "city": {
                "size_m": [240, 240],
                "building": {"coverage_ratio": 0.15, "density_per_km2": 80},
                "roads": {"grid_spacing_m": 60, "width_m": 10},
                "base_stations": {
                    "placement_family": "random_rooftop",
                    "density_per_km2": 12,
                    "height_m": 5,
                    "power_dbm": 44,
                    "min_separation_m": 40,
                    "sectors": 3,
                    "sector_azimuths_deg": [0, 120, 240],
                    "downtilt_deg": 0,
                    "random_offset_m": 2,
                },
                "task": {"altitude_m": 50, "altitude_range_m": [35, 65]},
            },
            "radio": {"enabled": True, "preset": "smoke", "tx_power_dbm": radio_power_dbm},
        }
    )


def test_base_station_manifest_is_reproducible_and_complete(tmp_path) -> None:
    config = _config()
    scene = generate_city(config.city, seed=config.seed)
    first = build_base_station_manifest(scene)
    second = build_base_station_manifest(scene)
    assert first == second
    assert first["site_count"] == len(scene.base_stations)
    assert first["sector_count"] == 3 * first["site_count"]
    assert [cell["azimuth_deg"] for cell in first["cells"]] == [0.0, 120.0, 240.0]
    assert {site["carrier_frequency_hz"] for site in first["sites"]} == {4.9e9}
    assert {site["bandwidth_hz"] for site in first["sites"]} == {100e6}
    assert {cell["carrier_frequency_hz"] for cell in first["cells"]} == {4.9e9}
    assert {cell["preset_id"] for cell in first["cells"]} == {"custom"}
    assert {cell["parameter_status"] for cell in first["cells"]} == {"simulation_proxy"}
    assert all("modified_fields" in site["metadata"] for site in first["sites"])
    path = tmp_path / "base_station_manifest.json"
    save_base_station_manifest(first, path)
    assert load_base_station_manifest(path, scene) == first


def test_rooftop_station_height_offset_and_separation_are_enforced() -> None:
    config = _config()
    scene = generate_city(config.city, seed=config.seed)
    buildings = {item["building_id"]: item for item in scene.buildings}
    for site in scene.base_stations:
        host = buildings[site["host_building_id"]]
        roof_z = float(host["center_m"][2]) + float(host["size_m"][2]) / 2.0
        assert site["position_m"][2] == pytest.approx(roof_z + config.city.base_stations.height_m)
        assert site["antenna_height_m"] == site["position_m"][2]
    scene.validate()


def test_tampered_base_station_manifest_is_rejected() -> None:
    config = _config()
    scene = generate_city(config.city, seed=config.seed)
    manifest = build_base_station_manifest(scene)
    tampered = copy.deepcopy(manifest)
    tampered["cells"][0]["azimuth_deg"] = 1.0
    with pytest.raises(ValueError, match="sector list"):
        validate_base_station_manifest(tampered, scene)


def test_radio_parameters_must_match_base_station_manifest() -> None:
    config = _config()
    scene = generate_city(config.city, seed=config.seed)
    manifest = build_base_station_manifest(scene)
    _validate_radio_station_contract(config.radio, manifest)
    mismatched = _config(radio_power_dbm=45.0)
    with pytest.raises(ValueError, match="Tx power"):
        _validate_radio_station_contract(mismatched.radio, manifest)


@pytest.mark.parametrize(
    ("config_path", "site_count", "height_m", "profile"),
    [
        (
            "configs/base_station_profiles/uma_reference_1km.yaml",
            5,
            25.0,
            "3gpp_uma_calibration_reference",
        ),
        (
            "configs/base_station_profiles/umi_reference_1km.yaml",
            30,
            10.0,
            "3gpp_umi_street_canyon_calibration_reference",
        ),
    ],
)
def test_reference_profiles_use_absolute_antenna_height(
    config_path: str,
    site_count: int,
    height_m: float,
    profile: str,
) -> None:
    config = load_config(config_path)
    scene = generate_city(config.city, seed=config.seed)
    manifest = build_base_station_manifest(scene)
    assert manifest["site_count"] == site_count
    assert manifest["sector_count"] == 3 * site_count
    assert {site["antenna_height_agl_m"] for site in manifest["sites"]} == {height_m}
    assert {site["deployment_profile"] for site in manifest["sites"]} == {profile}
    assert {site["carrier_frequency_hz"] for site in manifest["sites"]} == {4.9e9}
    assert {site["bandwidth_hz"] for site in manifest["sites"]} == {100e6}
    assert all(site["host_building_id"] is None for site in manifest["sites"])
    assert all(site["metadata"]["height_reference"] == "absolute_agl" for site in manifest["sites"])


@pytest.mark.parametrize(
    ("config_path", "frequency_hz", "sensing_enabled", "evidence_level"),
    [
        ("configs/base_station_profiles/low_band_wide_area_1km.yaml", 700e6, False, "A"),
        ("configs/base_station_profiles/sub6_low_altitude_macro_1km.yaml", 3.5e9, False, "A"),
        ("configs/base_station_profiles/isac_49_experimental_1km.yaml", 4.9e9, True, "B"),
        ("configs/base_station_profiles/mmwave_isac_experimental_1km.yaml", 26e9, True, "B"),
    ],
)
def test_low_altitude_presets_expose_provenance_and_capability_metadata(
    config_path: str,
    frequency_hz: float,
    sensing_enabled: bool,
    evidence_level: str,
) -> None:
    config = load_config(config_path)
    stations = config.city.base_stations
    assert stations.carrier_frequency_hz == frequency_hz
    assert stations.sensing_enabled is sensing_enabled
    assert stations.source_evidence_level == evidence_level
    assert stations.parameter_status == "simulation_proxy"
    assert stations.preset_id != "custom"
    assert stations.source_preset_id == stations.preset_id
    assert stations.reference_source
