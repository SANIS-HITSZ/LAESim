#!/usr/bin/env python3
"""Unit tests for mission sensor, dwell, and area-coverage constraints."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Multi_use"))

import space_mission_analyzer as analyzer  # noqa: E402
import space_mission_bridge as bridge  # noqa: E402


def context(**overrides):
    values = {
        "reference_lat": 0.0,
        "reference_lon": 0.0,
        "reference_alt": 0.0,
        "min_elevation_deg": 0.0,
        "max_range_m": None,
        "max_off_nadir_deg": None,
        "sensor_pointing_mode": "none",
        "sensor_half_angle_deg": None,
        "side_look_angle_deg": 0.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class SpaceMissionConstraintTests(unittest.TestCase):
    def setUp(self):
        self.sample = bridge.SpaceSample("", 0.0, 0.0, 500000.0)
        self.overhead = bridge.TargetSpec("Overhead", 0.0, 0.0, 0.0, "ground")
        self.offset = bridge.TargetSpec("Offset", 2.0, 0.0, 0.0, "ground")

    def test_nadir_fov_accepts_overhead_and_rejects_offset_target(self):
        args = context(sensor_pointing_mode="nadir", sensor_half_angle_deg=1.0)
        overhead = bridge.compute_access(self.sample, self.overhead, args)
        offset = bridge.compute_access(self.sample, self.offset, args)
        self.assertTrue(overhead.access)
        self.assertFalse(offset.access)
        self.assertEqual(offset.message, "outside_sensor_fov")
        self.assertGreater(offset.off_nadir_deg, 1.0)

    def test_target_track_respects_maximum_off_nadir(self):
        tracked = bridge.compute_access(
            self.sample,
            self.offset,
            context(
                sensor_pointing_mode="target-track",
                sensor_half_angle_deg=0.1,
                max_off_nadir_deg=30.0,
            ),
        )
        self.assertTrue(tracked.access)
        self.assertEqual(tracked.sensor_off_axis_deg, 0.0)
        limited = bridge.compute_access(
            self.sample,
            self.offset,
            context(sensor_pointing_mode="target-track", max_off_nadir_deg=1.0),
        )
        self.assertFalse(limited.access)
        self.assertEqual(limited.message, "off_nadir_exceeded")

    def test_side_look_boresight_can_center_offset_target(self):
        geometry = bridge.compute_access(self.sample, self.offset, context())
        side_look = bridge.compute_access(
            self.sample,
            self.offset,
            context(
                sensor_pointing_mode="side-look",
                side_look_angle_deg=geometry.off_nadir_deg,
                sensor_half_angle_deg=0.01,
            ),
        )
        self.assertTrue(side_look.access)
        self.assertAlmostEqual(side_look.sensor_off_axis_deg, 0.0, places=6)

    def test_minimum_dwell_rejects_short_window(self):
        target = analyzer.AnalysisTarget("T", 0.0, 0.0, min_dwell_s=20.0)
        short = analyzer.Window("Sat", "T", "T", "point", "a", "b", 10.0, 30.0, 500000.0)
        long = analyzer.Window("Sat", "T", "T", "point", "c", "d", 25.0, 40.0, 400000.0)
        qualified, rejected = analyzer.qualify_windows_by_dwell([short, long], [target])
        self.assertEqual(qualified, [long])
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["required_dwell_s"], 20.0)

    def test_area_coverage_fraction_is_reported(self):
        targets = [
            analyzer.AnalysisTarget(
                f"Area_P{index}", 0.0, 0.0, group="Area",
                target_type="area_grid", grid_point_count=4,
                min_area_coverage_fraction=0.5,
            )
            for index in range(4)
        ]
        samples = [
            {"time": "t0", "satellite": "Sat", "target": target.name, "access": index < 2}
            for index, target in enumerate(targets)
        ]
        rows = analyzer.build_area_coverage_samples(samples, targets)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["coverage_fraction"], 0.5)
        self.assertTrue(rows[0]["requirement_met"])


if __name__ == "__main__":
    unittest.main()
