#!/usr/bin/env python3
"""Unit tests for best-satellite selection and handover accounting."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from satellite_selector import BestSatelliteSelector, SatelliteCandidate  # noqa: E402


def candidate(name, elevation, range_m=500000.0):
    return SatelliteCandidate(name, elevation, range_m)


class BestSatelliteSelectorTests(unittest.TestCase):
    def test_selects_highest_elevation(self):
        selector = BestSatelliteSelector()
        result = selector.update(
            "Car",
            [candidate("Satellite", 10.0), candidate("Satellite2", 25.0)],
            now_s=0.0,
        )
        self.assertEqual(result.selected_satellite, "Satellite2")
        self.assertEqual(result.acquisition_count, 1)

    def test_hysteresis_and_minimum_hold_prevent_flapping(self):
        selector = BestSatelliteSelector(hysteresis_deg=2.0, minimum_hold_s=5.0)
        selector.update("Car", [candidate("Satellite", 20.0)], now_s=0.0)
        held = selector.update(
            "Car",
            [candidate("Satellite", 20.0), candidate("Satellite2", 30.0)],
            now_s=3.0,
        )
        self.assertEqual(held.selected_satellite, "Satellite")
        hysteresis = selector.update(
            "Car",
            [candidate("Satellite", 20.0), candidate("Satellite2", 21.0)],
            now_s=6.0,
        )
        self.assertEqual(hysteresis.selected_satellite, "Satellite")
        switched = selector.update(
            "Car",
            [candidate("Satellite", 20.0), candidate("Satellite2", 23.0)],
            now_s=7.0,
        )
        self.assertEqual(switched.selected_satellite, "Satellite2")
        self.assertEqual(switched.handover_count, 1)

    def test_outage_and_reacquisition_are_accounted(self):
        selector = BestSatelliteSelector()
        selector.update("Boat", [candidate("Satellite", 10.0)], now_s=0.0)
        down = selector.update("Boat", [], now_s=10.0)
        self.assertTrue(down.outage)
        up = selector.update("Boat", [candidate("Satellite2", 15.0)], now_s=14.5)
        self.assertEqual(up.interruption_s, 4.5)
        self.assertEqual(up.handover_count, 1)
        summary = selector.summary(now_s=20.0)["Boat"]
        self.assertEqual(summary["total_outage_s"], 4.5)
        self.assertEqual(summary["max_outage_s"], 4.5)
        self.assertEqual(summary["completed_outage_count"], 1)
        self.assertEqual(summary["mean_revisit_s"], 4.5)

    def test_unavailable_current_satellite_switches_immediately(self):
        selector = BestSatelliteSelector(hysteresis_deg=20.0, minimum_hold_s=100.0)
        selector.update("UAV", [candidate("Satellite", 30.0)], now_s=0.0)
        result = selector.update("UAV", [candidate("Satellite2", 5.0)], now_s=1.0)
        self.assertEqual(result.selected_satellite, "Satellite2")

    def test_initial_outage_is_included_in_revisit_statistics(self):
        selector = BestSatelliteSelector()
        selector.update("Car", [], now_s=0.0)
        result = selector.update("Car", [candidate("Satellite", 12.0)], now_s=6.0)
        self.assertEqual(result.interruption_s, 6.0)
        summary = selector.summary(now_s=7.0)["Car"]
        self.assertEqual(summary["completed_outage_count"], 1)
        self.assertEqual(summary["mean_revisit_s"], 6.0)


if __name__ == "__main__":
    unittest.main()
