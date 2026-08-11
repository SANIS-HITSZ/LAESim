#!/usr/bin/env python3
"""Unit tests for the runtime satellite-access network policy."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from space_access_policy import SpaceAccessPolicy  # noqa: E402


def make_config(fail_mode="closed"):
    return {
        "SpaceAccessPolicy": {
            "Enabled": True,
            "FailMode": fail_mode,
            "MaxStateAgeSeconds": 2.0,
            "Rules": [
                {
                    "Source": "Satellite",
                    "Destination": "Car",
                    "AccessTopic": "/space/Satellite/access/Car",
                    "Bidirectional": True,
                }
            ],
        }
    }


class SpaceAccessPolicyTests(unittest.TestCase):
    def test_unmatched_link_is_not_gated(self):
        policy = SpaceAccessPolicy(make_config(), ["Satellite", "Car", "UAV"])
        decision = policy.decide("UAV", "Car", now=10.0)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "link_not_gated")

    def test_closed_policy_blocks_missing_state(self):
        policy = SpaceAccessPolicy(make_config(), ["Satellite", "Car"])
        decision = policy.decide("Satellite", "Car", now=10.0)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "access_state_missing")

    def test_open_policy_allows_missing_state(self):
        policy = SpaceAccessPolicy(make_config("open"), ["Satellite", "Car"])
        self.assertTrue(policy.decide("Satellite", "Car", now=10.0).allowed)

    def test_live_access_controls_both_directions(self):
        policy = SpaceAccessPolicy(make_config(), ["Satellite", "Car"])
        topic = "/space/Satellite/access/Car"
        policy.update(topic, valid=True, access=True, received_at=10.0)
        self.assertTrue(policy.decide("Satellite", "Car", now=11.0).allowed)
        self.assertTrue(policy.decide("Car", "Satellite", now=11.0).allowed)

        policy.update(topic, valid=True, access=False, message="below elevation mask", received_at=12.0)
        decision = policy.decide("Satellite", "Car", now=12.5)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "below elevation mask")

    def test_stale_state_obeys_fail_mode(self):
        policy = SpaceAccessPolicy(make_config(), ["Satellite", "Car"])
        policy.update("/space/Satellite/access/Car", valid=True, access=True, received_at=10.0)
        decision = policy.decide("Satellite", "Car", now=12.1)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "access_state_stale")


if __name__ == "__main__":
    unittest.main()
