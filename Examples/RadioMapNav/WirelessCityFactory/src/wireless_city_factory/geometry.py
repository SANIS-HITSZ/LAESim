"""Shared two-dimensional road geometry checks for generation and validation."""

from __future__ import annotations

import math
from itertools import pairwise
from typing import Any


def road_intersects_xy_box(
    road: dict[str, Any],
    minimum_xy: tuple[float, float] | list[float],
    maximum_xy: tuple[float, float] | list[float],
    *,
    clearance_m: float = 0.5,
) -> bool:
    """Return whether a finite-width road touches an axis-aligned footprint."""
    margin = float(road["width_m"]) / 2.0 + float(clearance_m)
    rectangle = (
        float(minimum_xy[0]) - margin,
        float(maximum_xy[0]) + margin,
        float(minimum_xy[1]) - margin,
        float(maximum_xy[1]) + margin,
    )
    if road.get("axis") == "ring":
        center = road["center_m"]
        radii = road["radius_m"]
        cx, cy = float(center[0]), float(center[1])
        rx, ry = float(radii[0]), float(radii[1])
        points = [
            (
                cx + rx * math.cos(2.0 * math.pi * index / 256),
                cy + ry * math.sin(2.0 * math.pi * index / 256),
            )
            for index in range(257)
        ]
        return any(
            _segment_intersects_rectangle(first, second, rectangle)
            for first, second in pairwise(points)
        )
    start, end = road["start_m"], road["end_m"]
    return _segment_intersects_rectangle(
        (float(start[0]), float(start[1])),
        (float(end[0]), float(end[1])),
        rectangle,
    )


def _segment_intersects_rectangle(
    start: tuple[float, float],
    end: tuple[float, float],
    rectangle: tuple[float, float, float, float],
) -> bool:
    """Liang-Barsky clipping against xmin, xmax, ymin, ymax."""
    xmin, xmax, ymin, ymax = rectangle
    dx, dy = end[0] - start[0], end[1] - start[1]
    low, high = 0.0, 1.0
    for p, q in (
        (-dx, start[0] - xmin),
        (dx, xmax - start[0]),
        (-dy, start[1] - ymin),
        (dy, ymax - start[1]),
    ):
        if abs(p) < 1e-12:
            if q < 0.0:
                return False
            continue
        ratio = q / p
        if p < 0.0:
            low = max(low, ratio)
        else:
            high = min(high, ratio)
        if low > high:
            return False
    return True
