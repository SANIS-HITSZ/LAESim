#!/usr/bin/env python3
"""Unit tests for the satellite logical-link budget."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from network_backend import PacketRequest  # noqa: E402
from satellite_link_model import SatelliteLinkModel  # noqa: E402
from space_access_policy import AccessDecision  # noqa: E402


def make_model():
    return SatelliteLinkModel({"SatelliteLinkModel": {"Enabled": True}})


def make_request(size_bytes=1024):
    return PacketRequest("Satellite", "Car", "test", size_bytes, "link-budget-test")


def make_decision(range_m):
    return AccessDecision(
        allowed=True,
        reason="space_access_available",
        topic="/space/Satellite/access/Car",
        range_m=range_m,
    )


class SatelliteLinkModelTests(unittest.TestCase):
    def test_unmatched_link_uses_normal_backend(self):
        model = make_model()
        decision = AccessDecision(True, "link_not_gated")
        self.assertIsNone(model.build(make_request(), decision))

    def test_500km_link_budget_and_delay(self):
        link = make_model().build(make_request(), make_decision(500_000.0))
        self.assertIsNotNone(link)
        self.assertAlmostEqual(link.fspl_db, 153.28, places=1)
        self.assertAlmostEqual(link.propagation_delay_ns / 1e6, 1.668, places=2)
        self.assertGreater(link.snr_db, 10.0)
        self.assertLess(link.packet_error_rate, 1e-6)

    def test_range_reduces_link_margin(self):
        model = make_model()
        near = model.build(make_request(), make_decision(500_000.0))
        far = model.build(make_request(), make_decision(4_000_000.0))
        self.assertGreater(near.snr_db, far.snr_db)
        self.assertLess(near.packet_error_rate, far.packet_error_rate)
        self.assertEqual(far.packet_error_rate, 1.0)
        self.assertEqual(far.failure_reason, "link_budget")

    def test_invalid_geometry_is_rejected(self):
        with self.assertRaises(ValueError):
            make_model().build(make_request(), make_decision(float("nan")))


if __name__ == "__main__":
    unittest.main()
