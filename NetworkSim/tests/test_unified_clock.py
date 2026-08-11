#!/usr/bin/env python3
"""Unit tests for deterministic LAESim scenario-clock behavior."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from unified_clock import DeterministicClock  # noqa: E402


class DeterministicClockTests(unittest.TestCase):
    def test_rate_scales_monotonic_elapsed_time(self):
        clock = DeterministicClock(1000.0, rate=4.0, monotonic_s=10.0)
        self.assertEqual(clock.advance(12.5), 1010.0)

    def test_pause_resume_and_step(self):
        clock = DeterministicClock(1000.0, monotonic_s=0.0)
        clock.command("pause", 2.0)
        self.assertEqual(clock.advance(20.0), 1002.0)
        clock.command("step", 20.0, seconds=5.0)
        self.assertEqual(clock.scenario_time_s, 1007.0)
        clock.command("resume", 21.0)
        self.assertEqual(clock.advance(23.0), 1009.0)

    def test_set_rate_applies_after_prior_interval(self):
        clock = DeterministicClock(0.0, rate=1.0, monotonic_s=0.0)
        clock.command("set_rate", 2.0, rate=10.0)
        self.assertEqual(clock.scenario_time_s, 2.0)
        self.assertEqual(clock.advance(3.0), 12.0)

    def test_set_time_and_reset_are_deterministic(self):
        clock = DeterministicClock(100.0, monotonic_s=0.0)
        clock.command("set_time", 0.0, scenario_time_s=500.0)
        self.assertEqual(clock.scenario_time_s, 500.0)
        clock.command("reset", 0.0)
        self.assertEqual(clock.scenario_time_s, 100.0)


if __name__ == "__main__":
    unittest.main()
