from pathlib import Path

import pytest
from laesim_scene.config import GENERATOR_CONTRACT, config_from_mapping, load_config


def test_generator_contract_is_part_of_fingerprint_payload() -> None:
    config = config_from_mapping({})
    assert GENERATOR_CONTRACT == "wireless-city-generator-v9"
    assert config.fingerprint_payload()["generator_contract"] == GENERATOR_CONTRACT


def test_config_accepts_structured_yaml_shape() -> None:
    config = config_from_mapping({"global": {"seed": 11, "output": "out"}, "city": {"morphology": "voronoi"}, "radio": {"enabled": False}, "ue": {"enabled": True}})
    assert config.seed == 11
    assert config.city.morphology == "voronoi"
    assert config.ue.enabled


def test_city_validation_config_is_parsed() -> None:
    config = config_from_mapping(
        {
            "city": {
                "validation": {
                    "grid_resolution_m": 2,
                    "minimum_largest_component_fraction": 0.8,
                }
            }
        }
    )
    assert config.city.validation.grid_resolution_m == 2.0
    assert config.city.validation.minimum_largest_component_fraction == 0.8


def test_city_validation_fraction_must_be_bounded() -> None:
    with pytest.raises(ValueError, match="must be in"):
        config_from_mapping({"city": {"validation": {"minimum_largest_component_fraction": 1.1}}})


def test_street_grid_requires_absolute_agl_height() -> None:
    with pytest.raises(ValueError, match="absolute_agl"):
        config_from_mapping(
            {
                "city": {
                    "base_stations": {
                        "placement_family": "street_grid",
                        "height_reference": "mast_above_rooftop",
                    }
                }
            }
        )


def test_config_rejects_non_monotonic_radio_heights() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        config_from_mapping({"radio": {"heights_m": [35, 35]}})


def test_repository_ue_config_uses_portable_project_path() -> None:
    config = load_config(Path("configs/city_ue.yaml"))
    assert config.ue.editor_project == "Unreal/Environments/SceneGen/WirelessCityFactory.uproject"
    assert not Path(config.ue.editor_project).is_absolute()


def test_contract_smoke_keeps_formal_radio_parameters() -> None:
    config = load_config(Path("configs/city_radio_contract_smoke.yaml"))
    assert config.radio.frequency_hz == 4.9e9
    assert config.radio.bandwidth_hz == 100e6
    assert config.radio.tx_power_dbm == 53.0
    assert config.radio.antenna_model == "sector3-tr38901-8x4-dualpol"
    assert config.radio.cell_size_m == 40.0
    assert config.radio.samples_per_logical_sector == 256


def test_production_v1_radio_preset_is_frozen() -> None:
    config = config_from_mapping({"radio": {"enabled": True, "preset": "production_v1"}})
    assert config.radio.frequency_hz == 4.9e9
    assert config.radio.bandwidth_hz == 100e6
    assert config.radio.cell_size_m == 2.0
    assert config.radio.heights_m == (35.0, 65.0, 95.0, 115.0)
    assert config.radio.samples_per_logical_sector == 16_777_216
    assert config.radio.antenna_model == "sector3-tr38901-8x8-dualpol"


def test_setup_airsim_defaults_to_repository_host_project() -> None:
    script = Path("scripts/SetupLAESim.ps1").read_text(encoding="utf-8")
    assert "PythonClient\\airsim\\client.py" in script
    assert 'Join-Path $repositoryRoot "Unreal\\Environments\\SceneGen"' in script
