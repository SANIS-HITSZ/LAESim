#!/usr/bin/env python3
"""Unit tests for read-only space delivery configuration validation."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "NetworkSim" / "python"))

from space_delivery_validation import validate_files  # noqa: E402


def valid_settings():
    return {
        "SimMode": "AirGround",
        "ApiServerPortSatellite": 41491,
        "Vehicles": {
            "Satellite": {"VehicleType": "SimpleSatellite"},
            "Car": {"VehicleType": "PhysXCar"},
        },
        "NetworkSimulation": {
            "Backend": "ns3",
            "StepMs": 20,
            "MaxRangeMeters": 250,
            "WarmupSeconds": 1,
            "PacketTimeoutSeconds": 5,
            "SatelliteLinkModel": {
                "Enabled": True,
                "FrequencyHz": 2.2e9,
                "BandwidthHz": 5e6,
                "DataRateBps": 2e6,
                "NoiseFigureDb": 3,
                "PacketErrorModel": "none",
            },
            "SpaceAccessPolicy": {
                "Enabled": True,
                "FailMode": "closed",
                "Rules": [{
                    "Source": "Satellite",
                    "Destination": "Car",
                    "AccessTopic": "/space/Satellite/access/Car",
                }],
            },
        },
    }


class SpaceDeliveryValidationTests(unittest.TestCase):
    def write_json(self, directory, name, data):
        path = Path(directory) / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_valid_settings_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_json(directory, "settings.json", valid_settings())
            report = validate_files(path, expected_satellites=("Satellite",), expected_targets=("Car",), require_ns3=True)
            self.assertEqual(report.error_count, 0, report.to_dict())

    def test_unknown_rule_vehicle_fails(self):
        settings = valid_settings()
        settings["NetworkSimulation"]["SpaceAccessPolicy"]["Rules"][0]["Destination"] = "MissingCar"
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_json(directory, "settings.json", settings)
            report = validate_files(path)
            self.assertGreater(report.error_count, 0)
            self.assertIn("rule_destination", {item.code for item in report.findings})

    def test_satellite_link_requires_policy(self):
        settings = valid_settings()
        settings["NetworkSimulation"]["SpaceAccessPolicy"]["Enabled"] = False
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_json(directory, "settings.json", settings)
            report = validate_files(path)
            self.assertIn("link_requires_policy", {item.code for item in report.findings})

    def test_mission_relative_source_is_checked(self):
        mission = {
            "analysis": {
                "start_time": "2026-07-23T00:00:00Z",
                "duration_s": 60,
                "step_s": 10,
            },
            "satellites": [{"name": "Satellite", "provider": "tle", "tle": "missing.tle"}],
            "targets": [{"name": "Site", "latitude_deg": 22.5, "longitude_deg": 114.0}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_json(directory, "mission.json", mission)
            report = validate_files(mission_path=path)
            self.assertIn("mission_source_missing", {item.code for item in report.findings})


if __name__ == "__main__":
    unittest.main()
