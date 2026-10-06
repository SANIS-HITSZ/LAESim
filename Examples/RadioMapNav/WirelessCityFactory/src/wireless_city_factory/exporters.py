"""Portable mesh and lightweight preview exporters."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

from .schema import Scene

GEOMETRY_CONTRACT = "wireless-city-obj-watertight"
_FACES = ((0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 5, 4), (0, 1, 5), (1, 6, 5), (1, 2, 6), (2, 7, 6), (2, 3, 7), (3, 4, 7), (3, 0, 4))


def export_obj(scene: Scene, path: Path | str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Wireless City Factory canonical portable mesh", "# geometry contract: " + GEOMETRY_CONTRACT, "# units: metres; frame: right-handed, +z-up"]
    offset = 1
    ground_center = (scene.center_m[0], scene.center_m[1], -0.1)
    ground_size = (scene.size_m[0], scene.size_m[1], 0.2)
    offset = _append_box(lines, "ground", ground_center, ground_size, offset)
    for building in scene.buildings:
        offset = _append_box(lines, str(building["building_id"]), building["center_m"], building["size_m"], offset)
    target.write_text("\n".join(lines) + "\n", encoding="ascii")


def _append_box(lines: list[str], name: str, center: Sequence[float], size: Sequence[float], offset: int) -> int:
    cx, cy, cz = (float(value) for value in center)
    hx, hy, hz = (float(value) / 2.0 for value in size)
    vertices = ((cx - hx, cy - hy, cz - hz), (cx + hx, cy - hy, cz - hz), (cx + hx, cy + hy, cz - hz), (cx - hx, cy + hy, cz - hz), (cx - hx, cy - hy, cz + hz), (cx + hx, cy - hy, cz + hz), (cx + hx, cy + hy, cz + hz), (cx - hx, cy + hy, cz + hz))
    lines.append(f"o {name}")
    lines.extend(f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in vertices)
    lines.extend(f"f {offset + a} {offset + b} {offset + c}" for a, b, c in _FACES)
    return offset + len(vertices)


def export_preview_svg(scene: Scene, path: Path | str) -> None:
    """Write a dependency-free top-down image suitable for reports and smoke runs."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    width, height, margin = 1000, 1000, 30
    sx = (width - 2 * margin) / scene.size_m[0]
    sy = (height - 2 * margin) / scene.size_m[1]

    def point(x: float, y: float) -> tuple[float, float]:
        return margin + (x - scene.bounds_min_m[0]) * sx, height - margin - (y - scene.bounds_min_m[1]) * sy

    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="#f4f6f8"/>']
    for road in scene.roads:
        x0, y0 = point(float(road["start_m"][0]), float(road["start_m"][1]))
        x1, y1 = point(float(road["end_m"][0]), float(road["end_m"][1]))
        elements.append(f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" stroke="#c7cdd3" stroke-width="{max(1.0, float(road["width_m"]) * sx):.2f}"/>')
    for building in scene.buildings:
        cx, cy = point(float(building["center_m"][0]), float(building["center_m"][1]))
        w = float(building["size_m"][0]) * sx
        h = float(building["size_m"][1]) * sy
        elements.append(f'<rect x="{cx - w / 2:.2f}" y="{cy - h / 2:.2f}" width="{w:.2f}" height="{h:.2f}" fill="#64748b" stroke="#334155" stroke-width="1"/>')
    for station in scene.base_stations:
        x, y = point(float(station["position_m"][0]), float(station["position_m"][1]))
        elements.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="#dc2626"/>')
        for sector in station["sectors"]:
            angle = math.radians(float(sector["azimuth_deg"]))
            end_x = float(station["position_m"][0]) + 18.0 * math.cos(angle)
            end_y = float(station["position_m"][1]) + 18.0 * math.sin(angle)
            sx1, sy1 = point(end_x, end_y)
            elements.append(
                f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{sx1:.2f}" y2="{sy1:.2f}" '
                'stroke="#dc2626" stroke-width="2"/>'
            )
    for task in scene.tasks:
        for key, color in (("start_m", "#16a34a"), ("goal_m", "#2563eb")):
            x, y = point(float(task[key][0]), float(task[key][1]))
            elements.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="6" fill="{color}"/>')
    elements.append(f'<text x="{margin}" y="20" fill="#111827" font-family="sans-serif" font-size="16">{scene.scene_id}</text>')
    elements.append("</svg>")
    target.write_text("\n".join(elements) + "\n", encoding="ascii")
