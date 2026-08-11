#!/usr/bin/env python3
"""Best-satellite selection and handover statistics for LAESim."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class SatelliteCandidate:
    satellite: str
    elevation_deg: float
    range_m: float
    snr_db: float = float("nan")


@dataclass
class TargetSelectionState:
    selected_satellite: str = ""
    selected_since_s: float = 0.0
    last_selected_satellite: str = ""
    outage_started_s: Optional[float] = None
    handover_count: int = 0
    acquisition_count: int = 0
    outage_count: int = 0
    total_outage_s: float = 0.0
    max_outage_s: float = 0.0
    last_interruption_s: float = 0.0


@dataclass(frozen=True)
class SelectionResult:
    target: str
    selected_satellite: str
    previous_satellite: str
    changed: bool
    outage: bool
    handover_count: int
    acquisition_count: int
    interruption_s: float
    candidates: List[SatelliteCandidate]


class BestSatelliteSelector:
    def __init__(self, hysteresis_deg: float = 1.0, minimum_hold_s: float = 5.0):
        if hysteresis_deg < 0.0:
            raise ValueError("hysteresis_deg must be non-negative")
        if minimum_hold_s < 0.0:
            raise ValueError("minimum_hold_s must be non-negative")
        self.hysteresis_deg = float(hysteresis_deg)
        self.minimum_hold_s = float(minimum_hold_s)
        self.states: Dict[str, TargetSelectionState] = {}

    @staticmethod
    def _sort_candidates(candidates: Iterable[SatelliteCandidate]) -> List[SatelliteCandidate]:
        return sorted(
            candidates,
            key=lambda item: (-item.elevation_deg, item.range_m, item.satellite),
        )

    def update(
        self,
        target: str,
        candidates: Iterable[SatelliteCandidate],
        now_s: float,
    ) -> SelectionResult:
        ordered = self._sort_candidates(candidates)
        state = self.states.setdefault(target, TargetSelectionState(selected_since_s=now_s))
        previous = state.selected_satellite
        by_name = {candidate.satellite: candidate for candidate in ordered}
        selected = previous

        if not ordered:
            selected = ""
        elif previous not in by_name:
            selected = ordered[0].satellite
        else:
            current = by_name[previous]
            challenger = ordered[0]
            held_s = max(0.0, now_s - state.selected_since_s)
            if (
                challenger.satellite != previous
                and held_s >= self.minimum_hold_s
                and challenger.elevation_deg >= current.elevation_deg + self.hysteresis_deg
            ):
                selected = challenger.satellite

        if not ordered and not previous and state.outage_started_s is None:
            state.outage_started_s = now_s
            state.outage_count += 1

        changed = selected != previous
        interruption_s = 0.0
        if changed:
            if previous:
                state.last_selected_satellite = previous
            if not selected:
                if state.outage_started_s is None:
                    state.outage_started_s = now_s
                    state.outage_count += 1
            else:
                state.acquisition_count += 1
                if state.outage_started_s is not None:
                    interruption_s = max(0.0, now_s - state.outage_started_s)
                    state.total_outage_s += interruption_s
                    state.max_outage_s = max(state.max_outage_s, interruption_s)
                    state.outage_started_s = None
                if previous or state.last_selected_satellite:
                    state.handover_count += 1
                state.selected_since_s = now_s
            state.selected_satellite = selected
            state.last_interruption_s = interruption_s

        return SelectionResult(
            target=target,
            selected_satellite=state.selected_satellite,
            previous_satellite=previous,
            changed=changed,
            outage=not bool(state.selected_satellite),
            handover_count=state.handover_count,
            acquisition_count=state.acquisition_count,
            interruption_s=interruption_s,
            candidates=ordered,
        )

    def summary(self, now_s: Optional[float] = None) -> dict:
        result = {}
        for target, state in self.states.items():
            item = asdict(state)
            current_outage_s = 0.0
            if now_s is not None and state.outage_started_s is not None:
                current_outage_s = max(0.0, now_s - state.outage_started_s)
            item["current_outage_s"] = current_outage_s
            item["total_outage_s_including_current"] = state.total_outage_s + current_outage_s
            item["max_outage_s_including_current"] = max(state.max_outage_s, current_outage_s)
            completed_outages = max(
                0, state.outage_count - (1 if state.outage_started_s is not None else 0)
            )
            item["completed_outage_count"] = completed_outages
            item["mean_revisit_s"] = (
                state.total_outage_s / completed_outages if completed_outages else 0.0
            )
            item["max_revisit_s"] = state.max_outage_s
            result[target] = item
        return result
