from types import SimpleNamespace

import numpy as np
import pytest
from laesim_radio.radio import (
    _radio_metrics,
    _sionna_material,
    antenna_array_contract,
    build_multilayer_mesh,
    material_frequency_contract,
    reduce_triangle_values,
    sionna_orientation_rad,
)
from laesim_scene.city import generate_city
from laesim_scene.config import config_from_mapping


def test_multilayer_mesh_and_equal_area_reducer() -> None:
    config = config_from_mapping({"global": {"seed": 3}, "city": {"size_m": [100, 80], "building": {"coverage_ratio": 0.05, "density_per_km2": 10}, "task": {"altitude_m": 50, "altitude_range_m": [35, 65]}}, "radio": {"enabled": False}})
    scene = generate_city(config.city, seed=config.seed)
    mesh = build_multilayer_mesh(scene, [35.0, 50.0, 65.0], 20.0)
    assert mesh.faces.shape[0] == len(mesh.z_m) * len(mesh.x_m) * len(mesh.y_m) * 2
    raw = np.arange(2 * mesh.face_count, dtype=float).reshape(2, mesh.face_count)
    reduced = reduce_triangle_values(raw, mesh)
    assert reduced.shape == (2, len(mesh.z_m), len(mesh.y_m), len(mesh.x_m))
    assert np.allclose(reduced[0, 0, 0, 0], raw[0, 0:2].mean())


def test_formal_array_contract_has_64_dual_polarized_ports() -> None:
    contract = antenna_array_contract("sector3-tr38901-8x4-dualpol")
    assert contract["spatial_positions"] == 32
    assert contract["polarizations_per_position"] == 2
    assert contract["linear_port_count"] == 64
    assert contract["sionna_parameters"]["num_rows"] == 8
    assert contract["sionna_parameters"]["num_cols"] == 4
    assert contract["sionna_parameters"]["polarization"] == "cross"


def test_3gpp_calibration_array_proxy_has_128_dual_polarized_ports() -> None:
    contract = antenna_array_contract("sector3-tr38901-8x8-dualpol")
    assert contract["spatial_positions"] == 64
    assert contract["linear_port_count"] == 128
    assert contract["sionna_parameters"]["num_rows"] == 8
    assert contract["sionna_parameters"]["num_cols"] == 8
    assert contract["sionna_parameters"]["polarization"] == "cross"


def test_radio_metrics_are_stored_per_transmitter_as_wideband_rss() -> None:
    path_gain = np.asarray([[[[1e-8]]], [[[2e-8]]]])
    powers_w = np.asarray([1.0, 1.0])
    rss_dbm, sinr_linear, sinr_db = _radio_metrics(path_gain, powers_w, 1e-10)
    assert rss_dbm.shape == path_gain.shape
    assert sinr_linear.shape == path_gain.shape
    assert sinr_db.shape == path_gain.shape
    assert rss_dbm[:, 0, 0, 0] == pytest.approx([-50.0, -46.989700043])
    assert sinr_linear[1, 0, 0, 0] > sinr_linear[0, 0, 0, 0]


def test_material_frequency_contract_clamps_only_out_of_range_properties() -> None:
    low_band = material_frequency_contract(700e6)
    assert low_band["requested_frequency_hz"] == 700e6
    assert low_band["materials"]["concrete"]["evaluation_frequency_hz"] == 1e9
    assert low_band["materials"]["concrete"]["clamped"] is True
    assert low_band["materials"]["very_dry_ground"]["evaluation_frequency_hz"] == 1e9

    sub6 = material_frequency_contract(4.9e9)
    assert sub6["materials"]["concrete"]["clamped"] is False
    assert sub6["materials"]["very_dry_ground"]["clamped"] is False

    millimeter_wave = material_frequency_contract(26e9)
    assert millimeter_wave["materials"]["concrete"]["clamped"] is False
    assert millimeter_wave["materials"]["very_dry_ground"]["evaluation_frequency_hz"] == 10e9
    assert millimeter_wave["materials"]["very_dry_ground"]["clamped"] is True


def test_clamped_material_uses_sionna_21_nested_itu_function() -> None:
    calls = []

    def itu_material(material_type: str, frequency_hz: float) -> tuple[float, float]:
        calls.append((material_type, frequency_hz))
        return 4.0, 0.02

    class RadioMaterial:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    fake_rt = SimpleNamespace(
        itu_material=SimpleNamespace(itu_material=itu_material),
        RadioMaterial=RadioMaterial,
    )
    contract = material_frequency_contract(700e6)
    material = _sionna_material(fake_rt, "city-ground", "very_dry_ground", contract)

    assert calls == [("very_dry_ground", 1e9)]
    assert material.kwargs["relative_permittivity"] == 4.0
    assert material.kwargs["conductivity"] == 0.02


def test_sector_orientations_follow_sionna_zyx_order_and_distinct_boresights() -> None:
    downtilt = np.deg2rad(12.0)
    expected = [
        [np.cos(downtilt), 0.0, -np.sin(downtilt)],
        [-0.5 * np.cos(downtilt), np.sqrt(3) / 2 * np.cos(downtilt), -np.sin(downtilt)],
        [-0.5 * np.cos(downtilt), -np.sqrt(3) / 2 * np.cos(downtilt), -np.sin(downtilt)],
    ]
    boresights = []
    for azimuth in (0.0, 120.0, 240.0):
        z_angle, y_angle, x_angle = sionna_orientation_rad(azimuth, 12.0)
        assert x_angle == 0.0
        boresights.append([
            np.cos(z_angle) * np.cos(y_angle),
            np.sin(z_angle) * np.cos(y_angle),
            -np.sin(y_angle),
        ])
    assert np.allclose(np.asarray(boresights), np.asarray(expected))
    assert len({tuple(np.round(vector, 6)) for vector in boresights}) == 3
