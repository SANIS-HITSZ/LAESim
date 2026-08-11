#!/usr/bin/env python3
"""Deterministic scenario-clock state independent of ROS."""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass


@dataclass
class ClockStatus:
    scenario_time_s: float
    rate: float
    paused: bool
    sequence: int


class DeterministicClock:
    def __init__(self, start_time_s, rate=1.0, paused=False, monotonic_s=0.0):
        if rate <= 0.0:
            raise ValueError("clock rate must be positive")
        self.initial_time_s = float(start_time_s)
        self.scenario_time_s = float(start_time_s)
        self.rate = float(rate)
        self.paused = bool(paused)
        self.last_monotonic_s = float(monotonic_s)
        self.sequence = 0

    def advance(self, monotonic_s):
        monotonic_s = float(monotonic_s)
        elapsed_s = max(0.0, monotonic_s - self.last_monotonic_s)
        if not self.paused:
            self.scenario_time_s += elapsed_s * self.rate
        self.last_monotonic_s = monotonic_s
        return self.scenario_time_s

    def command(self, command, monotonic_s, **values):
        self.advance(monotonic_s)
        command = str(command).strip().lower()
        if command == "pause":
            self.paused = True
        elif command == "resume":
            self.paused = False
        elif command == "step":
            seconds = float(values.get("seconds", 1.0))
            if seconds <= 0.0:
                raise ValueError("step seconds must be positive")
            self.scenario_time_s += seconds
        elif command == "set_rate":
            rate = float(values["rate"])
            if rate <= 0.0:
                raise ValueError("clock rate must be positive")
            self.rate = rate
        elif command == "set_time":
            self.scenario_time_s = float(values["scenario_time_s"])
        elif command == "reset":
            self.scenario_time_s = self.initial_time_s
        else:
            raise ValueError(f"unsupported clock command: {command}")
        self.sequence += 1
        return self.status()

    def status(self):
        return ClockStatus(
            scenario_time_s=self.scenario_time_s,
            rate=self.rate,
            paused=self.paused,
            sequence=self.sequence,
        )

    def status_dict(self):
        result = asdict(self.status())
        result["scenario_time"] = (
            dt.datetime.fromtimestamp(self.scenario_time_s, tz=dt.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
        return result
