#!/usr/bin/env python3
"""Mission-level satellite access analysis for LAESim.

This script is the second-stage companion to space_mission_bridge.py. It runs a
time-stepped multi-satellite, multi-target access analysis and writes coverage
windows, revisit gaps, per-sample access data, and optional network-link windows.
"""

import argparse
import csv
import datetime as _dt
import json
import math
import os
import sys
from dataclasses import asdict, dataclass


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MULTI_USE = os.path.join(ROOT, "Multi_use")
if MULTI_USE not in sys.path:
    sys.path.insert(0, MULTI_USE)

import space_mission_bridge as bridge


@dataclass
class SatelliteSpec:
    name: str
    provider: str
    tle: str = ""
    satellite_name: str = ""
    satellite_index: int = 0
    csv: str = ""
    orekit_data: str = ""


@dataclass
class AnalysisTarget:
    name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float = 0.0
    kind: str = "ground"
    group: str = ""
    target_type: str = "point"
    grid_index: int = -1
    grid_point_count: int = 1
    min_elevation_deg: float = None
    max_range_m: float = None
    max_off_nadir_deg: float = None
    sensor_pointing_mode: str = "none"
    sensor_half_angle_deg: float = None
    side_look_angle_deg: float = 0.0
    min_dwell_s: float = 0.0
    min_area_coverage_fraction: float = 0.0


@dataclass
class Window:
    satellite: str
    target: str
    target_group: str
    target_type: str
    start: str
    stop: str
    duration_s: float
    max_elevation_deg: float
    min_range_m: float
    method: str = "sampled"
    required_dwell_s: float = 0.0


def parse_args():
    parser = argparse.ArgumentParser(description="Analyze multi-satellite access windows for LAESim space missions.")
    parser.add_argument("--mission", default=os.path.join(ROOT, "Multi_use", "space_mission.example.json"))
    parser.add_argument("--out", default=os.path.join(ROOT, "Multi_use", "space_mission_report"))
    parser.add_argument("--print-summary", action="store_true")
    return parser.parse_args()


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def resolve_path(path, base_dir):
    if not path:
        return ""
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(base_dir, path))


def make_namespace(mapping):
    class Namespace:
        pass
    obj = Namespace()
    for key, value in mapping.items():
        setattr(obj, key, value)
    return obj


def parse_satellites(config, base_dir):
    satellites = []
    default_orekit_data = resolve_path(config.get("orekit_data", ""), base_dir)
    for index, item in enumerate(config.get("satellites", [])):
        provider = item.get("provider", "tle")
        satellites.append(SatelliteSpec(
            name=item.get("name") or item.get("satellite_name") or f"Satellite{index + 1}",
            provider=provider,
            tle=resolve_path(item.get("tle", ""), base_dir),
            satellite_name=item.get("satellite_name", ""),
            satellite_index=int(item.get("satellite_index", index if provider == "tle" and not item.get("satellite_name") else 0)),
            csv=resolve_path(item.get("csv", ""), base_dir),
            orekit_data=resolve_path(item.get("orekit_data", ""), base_dir) or default_orekit_data))
    for constellation in config.get("constellations", []):
        provider = constellation.get("provider", "tle")
        if provider not in ("tle", "orekit-tle"):
            raise RuntimeError("Constellations support provider=tle or provider=orekit-tle.")
        tle_path = resolve_path(constellation.get("tle", ""), base_dir)
        entries = bridge.TleProvider._load_tles(tle_path)
        count = int(constellation.get("count", len(entries)))
        prefix = constellation.get("name_prefix", constellation.get("name", "Sat"))
        for local_index, entry in enumerate(entries[:count]):
            satellites.append(SatelliteSpec(
                name=f"{prefix}{local_index + 1}",
                provider=provider,
                tle=tle_path,
                satellite_name=entry[0],
                satellite_index=local_index,
                csv="",
                orekit_data=resolve_path(constellation.get("orekit_data", ""), base_dir) or default_orekit_data))
    if not satellites:
        raise RuntimeError("Mission config must contain at least one satellite.")
    return satellites


def area_grid_points(item):
    name = item.get("name", "Area")
    kind = item.get("kind", "area")
    center_lat = float(item["center_latitude_deg"])
    center_lon = float(item["center_longitude_deg"])
    alt = float(item.get("altitude_m", 0.0))
    width_km = float(item.get("width_km", 10.0))
    height_km = float(item.get("height_km", width_km))
    spacing_km = max(0.1, float(item.get("spacing_km", 2.0)))
    lat_step = spacing_km / 111.32
    lon_step = spacing_km / (111.32 * max(0.1, math.cos(math.radians(center_lat))))
    nx = max(1, int(math.floor(width_km / spacing_km)) + 1)
    ny = max(1, int(math.floor(height_km / spacing_km)) + 1)
    min_el = item.get("min_elevation_deg")
    max_range = item.get("max_range_m")
    constraints = parse_target_constraints(item)
    targets = []
    for iy in range(ny):
        for ix in range(nx):
            lat = center_lat + (iy - (ny - 1) / 2.0) * lat_step
            lon = center_lon + (ix - (nx - 1) / 2.0) * lon_step
            grid_index = iy * nx + ix
            targets.append(AnalysisTarget(
                name=f"{name}_P{grid_index + 1:03d}",
                latitude_deg=lat,
                longitude_deg=lon,
                altitude_m=alt,
                kind=kind,
                group=name,
                target_type="area_grid",
                grid_index=grid_index,
                grid_point_count=nx * ny,
                min_elevation_deg=float(min_el) if min_el is not None else None,
                max_range_m=float(max_range) if max_range is not None else None,
                **constraints))
    return targets


def parse_targets(config):
    targets = []
    for index, item in enumerate(config.get("targets", [])):
        name = item.get("name") or f"Target{index + 1}"
        target_type = item.get("type", "point")
        if target_type == "area_grid":
            targets.extend(area_grid_points(item))
            continue
        min_el = item.get("min_elevation_deg")
        max_range = item.get("max_range_m")
        constraints = parse_target_constraints(item)
        targets.append(AnalysisTarget(
            name=name,
            latitude_deg=float(item["latitude_deg"]),
            longitude_deg=float(item["longitude_deg"]),
            altitude_m=float(item.get("altitude_m", 0.0)),
            kind=item.get("kind", "ground"),
            group=name,
            target_type="point",
            grid_index=-1,
            grid_point_count=1,
            min_elevation_deg=float(min_el) if min_el is not None else None,
            max_range_m=float(max_range) if max_range is not None else None,
            **constraints))
    if not targets:
        raise RuntimeError("Mission config must contain at least one target.")
    return targets


def parse_target_constraints(item):
    pointing_mode = str(item.get("sensor_pointing_mode", "none")).lower()
    if pointing_mode not in ("none", "nadir", "side-look", "target-track"):
        raise RuntimeError(
            "sensor_pointing_mode must be none, nadir, side-look, or target-track"
        )
    half_angle = item.get("sensor_half_angle_deg")
    max_off_nadir = item.get("max_off_nadir_deg")
    values = {
        "sensor_half_angle_deg": float(half_angle) if half_angle is not None else None,
        "max_off_nadir_deg": float(max_off_nadir) if max_off_nadir is not None else None,
        "side_look_angle_deg": float(item.get("side_look_angle_deg", 0.0)),
        "min_dwell_s": float(item.get("min_dwell_s", 0.0)),
        "min_area_coverage_fraction": float(item.get("min_area_coverage_fraction", 0.0)),
    }
    if values["sensor_half_angle_deg"] is not None and values["sensor_half_angle_deg"] < 0.0:
        raise RuntimeError("sensor_half_angle_deg must be non-negative")
    if values["max_off_nadir_deg"] is not None and not 0.0 <= values["max_off_nadir_deg"] <= 180.0:
        raise RuntimeError("max_off_nadir_deg must be between 0 and 180")
    if not 0.0 <= values["side_look_angle_deg"] <= 180.0:
        raise RuntimeError("side_look_angle_deg must be between 0 and 180")
    if values["min_dwell_s"] < 0.0:
        raise RuntimeError("min_dwell_s must be non-negative")
    if not 0.0 <= values["min_area_coverage_fraction"] <= 1.0:
        raise RuntimeError("min_area_coverage_fraction must be between 0 and 1")
    values["sensor_pointing_mode"] = pointing_mode
    return values


def make_provider(spec):
    if spec.provider == "tle":
        if not spec.tle:
            raise RuntimeError(f"Satellite {spec.name} requires a TLE path.")
        return bridge.TleProvider(spec.tle, spec.satellite_name, spec.satellite_index)
    if spec.provider == "orekit-tle":
        if not spec.tle:
            raise RuntimeError(f"Satellite {spec.name} requires a TLE path.")
        return bridge.OrekitTleProvider(
            spec.tle, spec.satellite_name, spec.satellite_index, spec.orekit_data
        )
    if spec.provider == "csv":
        if not spec.csv:
            raise RuntimeError(f"Satellite {spec.name} requires a CSV path.")
        return bridge.CsvProvider(spec.csv, loop=False)
    raise RuntimeError(f"Unsupported analysis provider for {spec.name}: {spec.provider}")


def compute_access_for_target(sample, target, context):
    min_elevation = target.min_elevation_deg if target.min_elevation_deg is not None else context.min_elevation_deg
    local_context = make_namespace({
        "reference_lat": context.reference_lat,
        "reference_lon": context.reference_lon,
        "reference_alt": context.reference_alt,
        "min_elevation_deg": min_elevation,
        "max_range_m": target.max_range_m,
        "max_off_nadir_deg": target.max_off_nadir_deg,
        "sensor_pointing_mode": target.sensor_pointing_mode,
        "sensor_half_angle_deg": target.sensor_half_angle_deg,
        "side_look_angle_deg": target.side_look_angle_deg,
    })
    return bridge.compute_access(sample, target, local_context)


def close_window(active, stop_time):
    duration = max(0.0, (stop_time - active["start_dt"]).total_seconds())
    return Window(
        satellite=active["satellite"],
        target=active["target"],
        target_group=active["target_group"],
        target_type=active["target_type"],
        start=bridge.format_time(active["start_dt"]),
        stop=bridge.format_time(stop_time),
        duration_s=duration,
        max_elevation_deg=active["max_elevation_deg"],
        min_range_m=active["min_range_m"],
        method="sampled")


def orekit_event_windows(
    provider,
    satellite,
    target,
    context,
    start,
    stop,
    sample_access,
    max_check_s,
    threshold_s,
):
    min_elevation = (
        target.min_elevation_deg
        if target.min_elevation_deg is not None
        else context.min_elevation_deg
    )
    intervals = provider.access_windows(
        start,
        stop,
        target,
        min_elevation,
        max_check_s=max_check_s,
        threshold_s=threshold_s,
    )
    result = []
    access_samples = sample_access.get((satellite.name, target.name), [])
    for interval_start, interval_stop in intervals:
        inside = [
            access
            for sample_time, access in access_samples
            if interval_start <= sample_time <= interval_stop
        ]
        if inside:
            max_elevation = max(access.elevation_deg for access in inside)
            min_range = min(access.range_m for access in inside)
        else:
            midpoint = interval_start + (interval_stop - interval_start) / 2
            midpoint_access = compute_access_for_target(
                provider.sample(midpoint), target, context
            )
            max_elevation = midpoint_access.elevation_deg
            min_range = midpoint_access.range_m
        result.append(
            Window(
                satellite=satellite.name,
                target=target.name,
                target_group=target.group,
                target_type=target.target_type,
                start=bridge.format_time(interval_start),
                stop=bridge.format_time(interval_stop),
                duration_s=max(0.0, (interval_stop - interval_start).total_seconds()),
                max_elevation_deg=max_elevation,
                min_range_m=min_range,
                method="orekit-events",
            )
        )
    return result


def summarize_windows(
    windows, targets, satellites, analysis_start, analysis_stop, area_coverage_samples
):
    summary = {
        "analysis_start": bridge.format_time(analysis_start),
        "analysis_stop": bridge.format_time(analysis_stop),
        "satellite_count": len(satellites),
        "target_count": len(targets),
        "target_group_count": len({target.group for target in targets}),
        "targets": {},
        "target_groups": {},
    }
    by_target = {target.name: [] for target in targets}
    for window in windows:
        by_target.setdefault(window.target, []).append(window)

    total_s = max(1e-9, (analysis_stop - analysis_start).total_seconds())
    for target in targets:
        target_windows = sorted(by_target.get(target.name, []), key=lambda item: item.start)
        merged = []
        for window in target_windows:
            start = bridge.parse_time(window.start)
            stop = bridge.parse_time(window.stop)
            if not merged or start > merged[-1][1]:
                merged.append([start, stop])
            else:
                merged[-1][1] = max(merged[-1][1], stop)

        revisit_gaps = []
        previous_stop = None
        for start, stop in merged:
            if previous_stop is not None:
                revisit_gaps.append(max(0.0, (start - previous_stop).total_seconds()))
            previous_stop = stop
        covered_s = sum(max(0.0, (stop - start).total_seconds()) for start, stop in merged)
        summary["targets"][target.name] = {
            "kind": target.kind,
            "group": target.group,
            "type": target.target_type,
            "window_count": len(target_windows),
            "merged_window_count": len(merged),
            "total_access_s": covered_s,
            "coverage_fraction": min(1.0, covered_s / total_s),
            "max_revisit_s": max(revisit_gaps) if revisit_gaps else None,
            "mean_revisit_s": sum(revisit_gaps) / len(revisit_gaps) if revisit_gaps else None,
            "min_dwell_s": target.min_dwell_s,
            "max_range_m": target.max_range_m,
            "max_off_nadir_deg": target.max_off_nadir_deg,
            "sensor_pointing_mode": target.sensor_pointing_mode,
            "sensor_half_angle_deg": target.sensor_half_angle_deg,
            "side_look_angle_deg": target.side_look_angle_deg,
        }

    groups = {}
    for target in targets:
        groups.setdefault(target.group, []).append(target)
    for group_name, group_targets in groups.items():
        covered_points = 0
        total_access = 0.0
        revisit_values = []
        for target in group_targets:
            item = summary["targets"][target.name]
            if item["merged_window_count"] > 0:
                covered_points += 1
            total_access += item["total_access_s"]
            if item["max_revisit_s"] is not None:
                revisit_values.append(item["max_revisit_s"])
        first = group_targets[0]
        point_count = len(group_targets)
        summary["target_groups"][group_name] = {
            "kind": first.kind,
            "type": first.target_type,
            "point_count": point_count,
            "covered_point_count": covered_points,
            "spatial_coverage_fraction": covered_points / max(1, point_count),
            "mean_access_s_per_point": total_access / max(1, point_count),
            "max_revisit_s": max(revisit_values) if revisit_values else None,
            "mean_max_revisit_s": sum(revisit_values) / len(revisit_values) if revisit_values else None,
        }
        area_rows = [
            row for row in area_coverage_samples if row["target_group"] == group_name
        ]
        if area_rows:
            fractions = [row["coverage_fraction"] for row in area_rows]
            threshold = first.min_area_coverage_fraction
            summary["target_groups"][group_name].update({
                "min_area_coverage_fraction": threshold,
                "max_instantaneous_coverage_fraction": max(fractions),
                "mean_instantaneous_coverage_fraction": sum(fractions) / len(fractions),
                "samples_meeting_area_requirement": sum(
                    1 for value in fractions if value >= threshold
                ),
                "area_requirement_sample_fraction": sum(
                    1 for value in fractions if value >= threshold
                ) / len(fractions),
            })
    return summary


def build_area_coverage_samples(samples, targets):
    target_by_name = {target.name: target for target in targets}
    buckets = {}
    for sample in samples:
        target = target_by_name[sample["target"]]
        if target.target_type != "area_grid":
            continue
        key = (sample["time"], sample["satellite"], target.group)
        bucket = buckets.setdefault(key, {
            "time": sample["time"],
            "satellite": sample["satellite"],
            "target_group": target.group,
            "point_count": target.grid_point_count,
            "covered_point_count": 0,
            "min_area_coverage_fraction": target.min_area_coverage_fraction,
        })
        if sample["access"]:
            bucket["covered_point_count"] += 1
    result = []
    for bucket in buckets.values():
        bucket["coverage_fraction"] = (
            bucket["covered_point_count"] / max(1, bucket["point_count"])
        )
        bucket["requirement_met"] = (
            bucket["coverage_fraction"] >= bucket["min_area_coverage_fraction"]
        )
        result.append(bucket)
    result.sort(key=lambda item: (item["time"], item["satellite"], item["target_group"]))
    return result


def qualify_windows_by_dwell(windows, targets):
    target_by_name = {target.name: target for target in targets}
    qualified = []
    rejected = []
    for window in windows:
        target = target_by_name[window.target]
        window.required_dwell_s = target.min_dwell_s
        if window.duration_s + 1e-9 < target.min_dwell_s:
            rejected.append({
                "satellite": window.satellite,
                "target": window.target,
                "start": window.start,
                "stop": window.stop,
                "duration_s": window.duration_s,
                "required_dwell_s": target.min_dwell_s,
            })
        else:
            qualified.append(window)
    return qualified, rejected


def analyze(config_path):
    config = load_json(config_path)
    base_dir = os.path.dirname(os.path.abspath(config_path))
    analysis = config.get("analysis", {})
    start = bridge.parse_time(analysis.get("start_time", "2026-07-23T00:00:00Z"))
    duration_s = float(analysis.get("duration_s", 3600.0))
    step_s = float(analysis.get("step_s", 10.0))
    stop = start + _dt.timedelta(seconds=duration_s)
    if step_s <= 0.0:
        raise RuntimeError("analysis.step_s must be positive.")
    access_window_method = str(analysis.get("access_window_method", "auto")).lower()
    if access_window_method not in ("auto", "sampled", "orekit-events"):
        raise RuntimeError(
            "analysis.access_window_method must be auto, sampled, or orekit-events."
        )
    event_max_check_s = float(analysis.get("event_max_check_s", 60.0))
    event_threshold_s = float(analysis.get("event_threshold_s", 0.1))
    if event_max_check_s <= 0.0 or event_threshold_s <= 0.0:
        raise RuntimeError("Orekit event detection intervals must be positive.")

    reference = config.get("reference", {})
    context = make_namespace({
        "reference_lat": float(reference.get("latitude_deg", 22.591164)),
        "reference_lon": float(reference.get("longitude_deg", 113.975317)),
        "reference_alt": float(reference.get("altitude_m", 0.0)),
        "min_elevation_deg": float(analysis.get("min_elevation_deg", 5.0)),
    })

    satellites = parse_satellites(config, base_dir)
    targets = parse_targets(config)
    providers = {sat.name: make_provider(sat) for sat in satellites}
    active = {}
    windows = []
    samples = []
    sample_access = {}

    current = start
    while current <= stop:
        for sat in satellites:
            sample = providers[sat.name].sample(current)
            sample.satellite_name = sample.satellite_name or sat.name
            for target in targets:
                access = compute_access_for_target(sample, target, context)
                key = (sat.name, target.name)
                sample_access.setdefault(key, []).append((current, access))
                samples.append({
                    "time": bridge.format_time(current),
                    "satellite": sat.name,
                    "target": target.name,
                    "target_group": target.group,
                    "target_kind": target.kind,
                    "target_type": target.target_type,
                    "grid_index": target.grid_index,
                    "access": access.access,
                    "valid": access.valid,
                    "elevation_deg": access.elevation_deg,
                    "azimuth_deg": access.azimuth_deg,
                    "range_m": access.range_m,
                    "off_nadir_deg": access.off_nadir_deg,
                    "sensor_off_axis_deg": access.sensor_off_axis_deg,
                    "constraint_reason": access.message,
                    "latitude_deg": sample.latitude_deg,
                    "longitude_deg": sample.longitude_deg,
                    "altitude_m": sample.altitude_m,
                })

                if access.access:
                    if key not in active:
                        active[key] = {
                            "satellite": sat.name,
                            "target": target.name,
                            "target_group": target.group,
                            "target_type": target.target_type,
                            "start_dt": current,
                            "max_elevation_deg": access.elevation_deg,
                            "min_range_m": access.range_m,
                        }
                    else:
                        active[key]["max_elevation_deg"] = max(active[key]["max_elevation_deg"], access.elevation_deg)
                        active[key]["min_range_m"] = min(active[key]["min_range_m"], access.range_m)
                elif key in active:
                    windows.append(close_window(active.pop(key), current))
        current += _dt.timedelta(seconds=step_s)

    for item in list(active.values()):
        windows.append(close_window(item, stop))

    event_keys = set()
    event_windows = []
    event_fallbacks = []
    if access_window_method != "sampled":
        for sat in satellites:
            provider = providers[sat.name]
            if not isinstance(provider, bridge.OrekitTleProvider):
                continue
            for target in targets:
                key = (sat.name, target.name)
                sampled_constraints = []
                if target.max_range_m is not None:
                    sampled_constraints.append("max_range_m")
                if target.max_off_nadir_deg is not None:
                    sampled_constraints.append("max_off_nadir_deg")
                if target.sensor_pointing_mode != "none" and target.sensor_half_angle_deg is not None:
                    sampled_constraints.append("sensor_fov")
                if sampled_constraints:
                    event_fallbacks.append({
                        "satellite": sat.name,
                        "target": target.name,
                        "reason": ",".join(sampled_constraints) + " requires sampled combined constraints",
                    })
                    continue
                event_keys.add(key)
                event_windows.extend(
                    orekit_event_windows(
                        provider,
                        sat,
                        target,
                        context,
                        start,
                        stop,
                        sample_access,
                        event_max_check_s,
                        event_threshold_s,
                    )
                )
    if event_keys:
        windows = [
            window
            for window in windows
            if (window.satellite, window.target) not in event_keys
        ]
        windows.extend(event_windows)
    windows, dwell_rejections = qualify_windows_by_dwell(windows, targets)
    windows.sort(key=lambda item: (item.start, item.satellite, item.target))

    area_coverage_samples = build_area_coverage_samples(samples, targets)
    summary = summarize_windows(
        windows, targets, satellites, start, stop, area_coverage_samples
    )
    summary["access_window_method"] = access_window_method
    summary["orekit_event_link_count"] = len(event_keys)
    summary["orekit_event_fallbacks"] = event_fallbacks
    summary["dwell_rejection_count"] = len(dwell_rejections)
    summary["dwell_rejections"] = dwell_rejections
    network_links = [
        {
            "link_name": f"{window.satellite}->{window.target}",
            "src": window.satellite,
            "dst": window.target,
            "dst_group": window.target_group,
            "dst_type": window.target_type,
            "enabled_start": window.start,
            "enabled_stop": window.stop,
            "reason": "space_access",
            "window_method": window.method,
        }
        for window in windows
    ]
    return {
        "config": config,
        "summary": summary,
        "windows": [asdict(window) for window in windows],
        "samples": samples,
        "network_links": network_links,
        "targets": [asdict(target) for target in targets],
        "area_coverage_samples": area_coverage_samples,
    }


def make_geojson(result):
    features = []
    latest_by_satellite = {}
    for sample in result["samples"]:
        latest_by_satellite[sample["satellite"]] = sample

    for target in result["targets"]:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [target["longitude_deg"], target["latitude_deg"], target["altitude_m"]],
            },
            "properties": {
                "role": "target",
                "name": target["name"],
                "group": target["group"],
                "kind": target["kind"],
                "target_type": target["target_type"],
                "grid_index": target["grid_index"],
            },
        })

    for satellite, sample in latest_by_satellite.items():
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [sample["longitude_deg"], sample["latitude_deg"], sample["altitude_m"]],
            },
            "properties": {
                "role": "satellite_last_sample",
                "name": satellite,
                "time": sample["time"],
            },
        })

    for window in result["windows"]:
        target = next((item for item in result["targets"] if item["name"] == window["target"]), None)
        if not target:
            continue
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [target["longitude_deg"], target["latitude_deg"], target["altitude_m"]],
            },
            "properties": {
                "role": "access_window",
                "satellite": window["satellite"],
                "target": window["target"],
                "target_group": window["target_group"],
                "target_type": window["target_type"],
                "start": window["start"],
                "stop": window["stop"],
                "duration_s": window["duration_s"],
                "max_elevation_deg": window["max_elevation_deg"],
                "min_range_m": window["min_range_m"],
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def write_outputs(result, out_prefix):
    out_dir = os.path.dirname(os.path.abspath(out_prefix))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    summary_path = f"{out_prefix}_summary.json"
    windows_path = f"{out_prefix}_windows.csv"
    samples_path = f"{out_prefix}_samples.csv"
    links_path = f"{out_prefix}_network_links.json"
    geojson_path = f"{out_prefix}_geojson.json"
    area_coverage_path = f"{out_prefix}_area_coverage.csv"

    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(result["summary"], handle, ensure_ascii=False, indent=2, allow_nan=True)
    with open(links_path, "w", encoding="utf-8") as handle:
        json.dump(result["network_links"], handle, ensure_ascii=False, indent=2, allow_nan=True)
    with open(geojson_path, "w", encoding="utf-8") as handle:
        json.dump(make_geojson(result), handle, ensure_ascii=False, indent=2, allow_nan=True)

    with open(windows_path, "w", newline="", encoding="utf-8-sig") as handle:
        fields = ["satellite", "target", "target_group", "target_type", "start", "stop", "duration_s", "max_elevation_deg", "min_range_m", "method", "required_dwell_s"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(result["windows"])

    with open(samples_path, "w", newline="", encoding="utf-8-sig") as handle:
        fields = [
            "time", "satellite", "target", "target_group", "target_kind", "target_type", "grid_index", "access", "valid",
            "elevation_deg", "azimuth_deg", "range_m",
            "off_nadir_deg", "sensor_off_axis_deg", "constraint_reason",
            "latitude_deg", "longitude_deg", "altitude_m",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(result["samples"])

    with open(area_coverage_path, "w", newline="", encoding="utf-8-sig") as handle:
        fields = [
            "time", "satellite", "target_group", "point_count",
            "covered_point_count", "coverage_fraction",
            "min_area_coverage_fraction", "requirement_met",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(result["area_coverage_samples"])

    return (
        summary_path, windows_path, samples_path, links_path, geojson_path,
        area_coverage_path,
    )


def print_summary(result):
    summary = result["summary"]
    print(f"Analysis: {summary['analysis_start']} -> {summary['analysis_stop']}")
    print(f"Satellites: {summary['satellite_count']}, target points: {summary['target_count']}, groups: {summary['target_group_count']}")
    for target, item in summary["target_groups"].items():
        revisit = item["max_revisit_s"]
        revisit_text = "n/a" if revisit is None else f"{revisit:.1f}s"
        print(
            f"  {target} ({item['kind']}/{item['type']}): points={item['point_count']} "
            f"spatial_coverage={item['spatial_coverage_fraction']:.3f} "
            f"mean_access={item['mean_access_s_per_point']:.1f}s "
            f"max_revisit={revisit_text}")


def main():
    args = parse_args()
    result = analyze(args.mission)
    paths = write_outputs(result, args.out)
    if args.print_summary:
        print_summary(result)
    for path in paths:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
