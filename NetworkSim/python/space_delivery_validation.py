#!/usr/bin/env python3
"""Read-only validation for LAESim space mission and network settings."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str
    location: str = ""


class ValidationReport:
    def __init__(self):
        self.findings: List[Finding] = []

    def add(self, level, code, message, location=""):
        self.findings.append(Finding(level, code, message, location))

    def error(self, code, message, location=""):
        self.add("error", code, message, location)

    def warning(self, code, message, location=""):
        self.add("warning", code, message, location)

    def info(self, code, message, location=""):
        self.add("info", code, message, location)

    @property
    def error_count(self):
        return sum(item.level == "error" for item in self.findings)

    @property
    def warning_count(self):
        return sum(item.level == "warning" for item in self.findings)

    def to_dict(self):
        return {
            "valid": self.error_count == 0,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "findings": [asdict(item) for item in self.findings],
        }


def load_json(path: Path, report: ValidationReport, label: str):
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        report.error(f"{label}_missing", f"File does not exist: {path}", str(path))
        return None
    except json.JSONDecodeError as error:
        report.error(
            f"{label}_json_invalid",
            f"Invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}",
            str(path),
        )
        return None
    except OSError as error:
        report.error(f"{label}_unreadable", str(error), str(path))
        return None
    if not isinstance(data, dict):
        report.error(f"{label}_root_type", "JSON root must be an object", str(path))
        return None
    return data


def positive_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def validate_positive_fields(mapping, names, report, prefix):
    for name in names:
        if name in mapping and not positive_number(mapping[name]):
            report.error("positive_number_required", f"{prefix}.{name} must be positive", f"{prefix}.{name}")


def validate_settings(
    settings: dict,
    report: ValidationReport,
    expected_satellites: Iterable[str] = (),
    expected_targets: Iterable[str] = (),
    require_ns3: bool = False,
):
    vehicles = settings.get("Vehicles")
    if not isinstance(vehicles, dict) or not vehicles:
        report.error("vehicles_missing", "Vehicles must be a non-empty object", "Vehicles")
        return

    satellite_names = []
    for name, config in vehicles.items():
        if not isinstance(config, dict):
            report.error("vehicle_invalid", f"Vehicle {name} must be an object", f"Vehicles.{name}")
            continue
        vehicle_type = str(config.get("VehicleType", ""))
        if vehicle_type == "SimpleSatellite" or name.lower().startswith("satellite"):
            satellite_names.append(name)
            if vehicle_type and vehicle_type != "SimpleSatellite":
                report.warning(
                    "satellite_type_unexpected",
                    f"{name} is treated as a satellite but VehicleType is {vehicle_type}",
                    f"Vehicles.{name}.VehicleType",
                )

    if not satellite_names:
        report.error("satellite_missing", "At least one SimpleSatellite vehicle is required", "Vehicles")
    for name in expected_satellites:
        if name not in vehicles:
            report.error("expected_satellite_missing", f"Expected satellite is not configured: {name}", f"Vehicles.{name}")
        elif str(vehicles[name].get("VehicleType", "")) not in ("", "SimpleSatellite"):
            report.error("expected_satellite_type", f"{name} must use VehicleType SimpleSatellite", f"Vehicles.{name}.VehicleType")
    for name in expected_targets:
        if name not in vehicles:
            report.error("expected_target_missing", f"Expected target is not configured: {name}", f"Vehicles.{name}")

    sim_mode = settings.get("SimMode")
    if sim_mode is not None and sim_mode != "AirGround":
        report.warning("sim_mode", "Space demonstrations are normally run with SimMode AirGround", "SimMode")
    if any(str(config.get("VehicleType", "")) == "SimpleSatellite" for config in vehicles.values() if isinstance(config, dict)):
        if "ApiServerPortSatellite" not in settings:
            report.warning("satellite_port_missing", "ApiServerPortSatellite is not explicitly configured", "ApiServerPortSatellite")

    network = settings.get("NetworkSimulation")
    if not isinstance(network, dict):
        report.error("network_missing", "NetworkSimulation must be configured for the delivery demo", "NetworkSimulation")
        return
    backend = str(network.get("Backend", "none")).lower()
    if backend not in ("none", "ns3"):
        report.error("backend_invalid", f"Unsupported NetworkSimulation.Backend: {backend}", "NetworkSimulation.Backend")
    if require_ns3 and backend != "ns3":
        report.error("ns3_required", "NetworkSimulation.Backend must be ns3 for this check", "NetworkSimulation.Backend")
    validate_positive_fields(
        network,
        ("StepMs", "MaxRangeMeters", "WarmupSeconds", "PacketTimeoutSeconds"),
        report,
        "NetworkSimulation",
    )

    link = network.get("SatelliteLinkModel", {})
    policy = network.get("SpaceAccessPolicy", {})
    if not isinstance(link, dict):
        report.error("satellite_link_invalid", "SatelliteLinkModel must be an object", "NetworkSimulation.SatelliteLinkModel")
        link = {}
    if not isinstance(policy, dict):
        report.error("space_policy_invalid", "SpaceAccessPolicy must be an object", "NetworkSimulation.SpaceAccessPolicy")
        policy = {}
    link_enabled = bool(link.get("Enabled", False))
    policy_enabled = bool(policy.get("Enabled", False))
    if link_enabled and not policy_enabled:
        report.error(
            "link_requires_policy",
            "SatelliteLinkModel.Enabled requires SpaceAccessPolicy.Enabled",
            "NetworkSimulation.SpaceAccessPolicy.Enabled",
        )
    if not link_enabled:
        report.warning("satellite_link_disabled", "SatelliteLinkModel is disabled", "NetworkSimulation.SatelliteLinkModel.Enabled")
    validate_positive_fields(
        link,
        ("FrequencyHz", "BandwidthHz", "DataRateBps", "NoiseFigureDb"),
        report,
        "NetworkSimulation.SatelliteLinkModel",
    )
    packet_error_model = str(link.get("PacketErrorModel", "bpsk")).lower()
    if packet_error_model not in ("bpsk", "none"):
        report.error("packet_error_model", "PacketErrorModel must be bpsk or none", "NetworkSimulation.SatelliteLinkModel.PacketErrorModel")

    fail_mode = str(policy.get("FailMode", "closed")).lower()
    if fail_mode not in ("open", "closed"):
        report.error("fail_mode", "SpaceAccessPolicy.FailMode must be open or closed", "NetworkSimulation.SpaceAccessPolicy.FailMode")
    if fail_mode == "open":
        report.warning("fail_open", "FailMode=open allows traffic when access state is missing or invalid", "NetworkSimulation.SpaceAccessPolicy.FailMode")
    rules = policy.get("Rules", [])
    if policy_enabled and not isinstance(rules, list):
        report.error("rules_invalid", "SpaceAccessPolicy.Rules must be an array", "NetworkSimulation.SpaceAccessPolicy.Rules")
        rules = []
    if policy_enabled and not rules:
        report.error("rules_empty", "Enabled SpaceAccessPolicy requires at least one rule", "NetworkSimulation.SpaceAccessPolicy.Rules")
    pairs = set()
    satellite_rule_sources = set()
    for index, rule in enumerate(rules):
        location = f"NetworkSimulation.SpaceAccessPolicy.Rules[{index}]"
        if not isinstance(rule, dict):
            report.error("rule_invalid", "Rule must be an object", location)
            continue
        source = str(rule.get("Source", "")).strip()
        destination = str(rule.get("Destination", "")).strip()
        topic = str(rule.get("AccessTopic", f"/space/{source}/access/{destination}"))
        if not source or source not in vehicles:
            report.error("rule_source", f"Unknown rule source: {source or '<empty>'}", location + ".Source")
        if not destination or destination not in vehicles:
            report.error("rule_destination", f"Unknown rule destination: {destination or '<empty>'}", location + ".Destination")
        if source == destination and source:
            report.error("rule_self_link", "Source and Destination must differ", location)
        if not topic.startswith("/"):
            report.error("rule_topic", "AccessTopic must start with /", location + ".AccessTopic")
        pair = (source, destination)
        if pair in pairs:
            report.error("rule_duplicate", f"Duplicate access rule: {source}->{destination}", location)
        pairs.add(pair)
        if source in satellite_names:
            satellite_rule_sources.add(source)
        if bool(rule.get("Bidirectional", False)) and (destination, source) in pairs:
            report.warning("bidirectional_duplicate", f"Explicit reverse rule overlaps Bidirectional rule for {source}<->{destination}", location)
    for name in satellite_names:
        if policy_enabled and name not in satellite_rule_sources:
            report.warning("satellite_rule_missing", f"No outgoing access rule is configured for {name}", f"Vehicles.{name}")

    report.info(
        "settings_summary",
        f"Configured vehicles={len(vehicles)}, satellites={len(satellite_names)}, access_rules={len(rules)}",
    )


def parse_iso_time(value):
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return dt.datetime.fromisoformat(text)


def validate_mission(mission: dict, mission_path: Path, report: ValidationReport):
    analysis = mission.get("analysis")
    if not isinstance(analysis, dict):
        report.error("analysis_missing", "Mission analysis must be an object", "analysis")
        analysis = {}
    try:
        parse_iso_time(analysis.get("start_time", ""))
    except (TypeError, ValueError):
        report.error("start_time", "analysis.start_time must be ISO-8601", "analysis.start_time")
    validate_positive_fields(analysis, ("duration_s", "step_s"), report, "analysis")
    min_elevation = analysis.get("min_elevation_deg", 5.0)
    if not isinstance(min_elevation, (int, float)) or not -90.0 <= min_elevation <= 90.0:
        report.error("min_elevation", "analysis.min_elevation_deg must be between -90 and 90", "analysis.min_elevation_deg")

    satellites = mission.get("satellites", [])
    if not isinstance(satellites, list) or not satellites:
        report.error("mission_satellites", "Mission must contain at least one satellite", "satellites")
        satellites = []
    names = set()
    allowed_providers = {"tle", "orekit-tle", "csv", "mock"}
    for index, satellite in enumerate(satellites):
        location = f"satellites[{index}]"
        if not isinstance(satellite, dict):
            report.error("mission_satellite_invalid", "Satellite must be an object", location)
            continue
        name = str(satellite.get("name", "")).strip()
        provider = str(satellite.get("provider", "tle")).lower()
        if not name:
            report.error("mission_satellite_name", "Satellite name is required", location + ".name")
        elif name in names:
            report.error("mission_satellite_duplicate", f"Duplicate satellite name: {name}", location + ".name")
        names.add(name)
        if provider not in allowed_providers:
            report.error("mission_provider", f"Unsupported provider: {provider}", location + ".provider")
            continue
        path_key = "csv" if provider == "csv" else "tle" if provider in ("tle", "orekit-tle") else ""
        if path_key:
            value = str(satellite.get(path_key, "")).strip()
            if not value:
                report.error("mission_source_missing", f"Provider {provider} requires {path_key}", location + f".{path_key}")
            else:
                source_path = Path(value).expanduser()
                if not source_path.is_absolute():
                    source_path = mission_path.parent / source_path
                if not source_path.is_file():
                    report.error("mission_source_missing", f"Source file does not exist: {source_path}", location + f".{path_key}")

    targets = mission.get("targets", [])
    if not isinstance(targets, list) or not targets:
        report.error("mission_targets", "Mission must contain at least one target", "targets")
        targets = []
    target_names = set()
    for index, target in enumerate(targets):
        location = f"targets[{index}]"
        if not isinstance(target, dict):
            report.error("mission_target_invalid", "Target must be an object", location)
            continue
        name = str(target.get("name", "")).strip()
        if not name:
            report.error("mission_target_name", "Target name is required", location + ".name")
        elif name in target_names:
            report.error("mission_target_duplicate", f"Duplicate target name: {name}", location + ".name")
        target_names.add(name)
        latitude = target.get("latitude_deg", target.get("center_latitude_deg"))
        longitude = target.get("longitude_deg", target.get("center_longitude_deg"))
        if not isinstance(latitude, (int, float)) or not -90.0 <= latitude <= 90.0:
            report.error("target_latitude", "Target latitude must be between -90 and 90", location)
        if not isinstance(longitude, (int, float)) or not -180.0 <= longitude <= 180.0:
            report.error("target_longitude", "Target longitude must be between -180 and 180", location)
        if target.get("type") == "area_grid":
            validate_positive_fields(target, ("width_km", "height_km", "spacing_km"), report, location)

    report.info(
        "mission_summary",
        f"Configured mission satellites={len(satellites)}, targets={len(targets)}",
    )


def validate_files(
    settings_path: Optional[Path] = None,
    mission_path: Optional[Path] = None,
    expected_satellites: Iterable[str] = (),
    expected_targets: Iterable[str] = (),
    require_ns3: bool = False,
):
    report = ValidationReport()
    if settings_path is not None:
        settings_path = settings_path.expanduser().resolve()
        settings = load_json(settings_path, report, "settings")
        if settings is not None:
            validate_settings(settings, report, expected_satellites, expected_targets, require_ns3)
    if mission_path is not None:
        mission_path = mission_path.expanduser().resolve()
        mission = load_json(mission_path, report, "mission")
        if mission is not None:
            validate_mission(mission, mission_path, report)
    if settings_path is None and mission_path is None:
        report.error("input_missing", "Specify --settings and/or --mission")
    return report


def main():
    parser = argparse.ArgumentParser(description="Validate LAESim space delivery configuration without modifying it.")
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--mission", type=Path)
    parser.add_argument("--expect-satellite", action="append", default=[])
    parser.add_argument("--expect-target", action="append", default=[])
    parser.add_argument("--require-ns3", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failure.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = validate_files(
        args.settings,
        args.mission,
        args.expect_satellite,
        args.expect_target,
        args.require_ns3,
    )
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        for item in report.findings:
            location = f" [{item.location}]" if item.location else ""
            print(f"{item.level.upper():7s} {item.code}: {item.message}{location}")
        print(f"Validation: errors={report.error_count}, warnings={report.warning_count}")
    raise SystemExit(1 if report.error_count or (args.strict and report.warning_count) else 0)


if __name__ == "__main__":
    main()
