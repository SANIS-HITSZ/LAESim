#!/usr/bin/env python3
"""Runtime satellite-access policy for LAESim network messages."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class AccessRule:
    source: str
    destination: str
    topic: str
    bidirectional: bool = True

    def matches(self, source: str, destination: str) -> bool:
        if source == self.source and destination == self.destination:
            return True
        return self.bidirectional and source == self.destination and destination == self.source


@dataclass
class AccessSnapshot:
    valid: bool
    access: bool
    received_at: float
    elevation_deg: float = float("nan")
    range_m: float = float("nan")
    message: str = ""


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str
    topic: str = ""
    elevation_deg: float = float("nan")
    range_m: float = float("nan")


class SpaceAccessPolicy:
    """Gates selected LAESim links using live SpaceAccessState messages."""

    def __init__(self, network_config: dict, node_names: Iterable[str]):
        config = network_config.get("SpaceAccessPolicy", {})
        self.enabled = bool(config.get("Enabled", False))
        self.fail_mode = str(config.get("FailMode", "closed")).strip().lower()
        self.max_state_age_s = float(config.get("MaxStateAgeSeconds", 2.0))
        self.rules: List[AccessRule] = []
        self.snapshots: Dict[str, AccessSnapshot] = {}

        if self.fail_mode not in ("open", "closed"):
            raise ValueError("NetworkSimulation.SpaceAccessPolicy.FailMode must be 'open' or 'closed'")
        if self.max_state_age_s <= 0.0:
            raise ValueError("NetworkSimulation.SpaceAccessPolicy.MaxStateAgeSeconds must be positive")

        known_nodes = set(node_names)
        for index, item in enumerate(config.get("Rules", [])):
            source = str(item.get("Source", "")).strip()
            destination = str(item.get("Destination", "")).strip()
            if not source or not destination:
                raise ValueError(f"SpaceAccessPolicy rule {index} requires Source and Destination")
            if source not in known_nodes or destination not in known_nodes:
                raise ValueError(
                    f"SpaceAccessPolicy rule {index} references an unknown LAESim vehicle: "
                    f"{source}->{destination}"
                )
            topic = str(
                item.get("AccessTopic", f"/space/{source}/access/{destination}")
            ).strip()
            if not topic.startswith("/"):
                topic = "/" + topic
            self.rules.append(
                AccessRule(
                    source=source,
                    destination=destination,
                    topic=topic,
                    bidirectional=bool(item.get("Bidirectional", True)),
                )
            )

        if self.enabled and not self.rules:
            raise ValueError("SpaceAccessPolicy is enabled but Rules is empty")

    @property
    def subscription_topics(self) -> Tuple[str, ...]:
        return tuple(dict.fromkeys(rule.topic for rule in self.rules)) if self.enabled else ()

    def update(
        self,
        topic: str,
        valid: bool,
        access: bool,
        elevation_deg: float = float("nan"),
        range_m: float = float("nan"),
        message: str = "",
        received_at: Optional[float] = None,
    ) -> None:
        self.snapshots[topic] = AccessSnapshot(
            valid=bool(valid),
            access=bool(access),
            received_at=time.monotonic() if received_at is None else float(received_at),
            elevation_deg=float(elevation_deg),
            range_m=float(range_m),
            message=str(message),
        )

    def decide(
        self,
        source: str,
        destination: str,
        now: Optional[float] = None,
    ) -> AccessDecision:
        if not self.enabled:
            return AccessDecision(True, "policy_disabled")

        rule = next((item for item in self.rules if item.matches(source, destination)), None)
        if rule is None:
            return AccessDecision(True, "link_not_gated")

        snapshot = self.snapshots.get(rule.topic)
        fallback_allowed = self.fail_mode == "open"
        if snapshot is None:
            return AccessDecision(fallback_allowed, "access_state_missing", rule.topic)

        current = time.monotonic() if now is None else float(now)
        if current - snapshot.received_at > self.max_state_age_s:
            return AccessDecision(
                fallback_allowed,
                "access_state_stale",
                rule.topic,
                snapshot.elevation_deg,
                snapshot.range_m,
            )
        if not snapshot.valid:
            return AccessDecision(
                fallback_allowed,
                "access_state_invalid",
                rule.topic,
                snapshot.elevation_deg,
                snapshot.range_m,
            )
        if not snapshot.access:
            return AccessDecision(
                False,
                snapshot.message or "space_access_unavailable",
                rule.topic,
                snapshot.elevation_deg,
                snapshot.range_m,
            )
        return AccessDecision(
            True,
            "space_access_available",
            rule.topic,
            snapshot.elevation_deg,
            snapshot.range_m,
        )
