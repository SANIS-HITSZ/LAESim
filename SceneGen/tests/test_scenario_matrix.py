from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_scenario_matrix_v1_references_frozen_profiles_and_existing_configs() -> None:
    matrix = yaml.safe_load(
        (PROJECT_ROOT / "configs" / "scenario_matrix_v1.yaml").read_text(encoding="utf-8")
    )

    assert matrix["status"] == "radio_v4_regeneration_required"
    assert matrix["radio_map"]["production_sampling_budget"]["status"] == (
        "invalidated_by_radio_v4_orientation_fix"
    )
    assert matrix["city_set"]["profiles"] == [
        "dense_highrise_grid",
        "irregular_midrise",
        "sparse_suburban",
    ]
    assert matrix["city_set"]["seeds"] == [20260821, 20260822, 20260823]
    assert matrix["radio_map"]["measurement_heights_m"] == [35, 65, 95, 115]
    assert matrix["radio_map"]["cell_size_m"] == 2
    sampling = matrix["radio_map"]["production_sampling_budget"]
    assert sampling["status"] == "invalidated_by_radio_v4_orientation_fix"
    assert sampling["samples_per_logical_sector"] == 16_777_216
    assert sampling["preset"] == "production_v1"

    pairings = matrix["pairings"]
    assert {item["city_profile"] for item in pairings} == set(matrix["city_set"]["profiles"])
    assert pairings[-1]["rationale"].endswith("not_3gpp_rma")

    for profile in matrix["base_station_profiles"].values():
        config_path = PROJECT_ROOT.parent / profile["config"]
        assert config_path.is_file()
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert config["city"]["base_stations"]["deployment_profile"] == profile["source_label"]


def test_city_set_v1_has_no_temporary_base_station_deployment() -> None:
    config = yaml.safe_load(
        (PROJECT_ROOT / "configs" / "city_set_v1.yaml").read_text(encoding="utf-8")
    )

    base_stations = config["city"]["base_stations"]
    assert base_stations["deployment_profile"] == "unassigned_city_geometry_only"
    assert base_stations["density_per_km2"] == 0
