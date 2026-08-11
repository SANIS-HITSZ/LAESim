#!/usr/bin/env python3
"""Read-only environment and live-stack diagnostics for the LAESim space demo."""

from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "NetworkSim" / "python"))

from space_delivery_validation import validate_files  # noqa: E402


@dataclass(frozen=True)
class Check:
    status: str
    name: str
    detail: str


def find_settings():
    candidates = []
    if os.name == "nt":
        candidates.append(Path.home() / "Documents" / "AirSim" / "settings.json")
    else:
        candidates.extend(Path(path) for path in glob.glob("/mnt/c/Users/*/Documents/AirSim/settings.json"))
        candidates.append(Path.home() / "Documents" / "AirSim" / "settings.json")
    return next((path for path in candidates if path.is_file()), None)


def run(command, timeout=8.0):
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)


def add(checks, condition, name, ok_detail, fail_detail, required=True):
    checks.append(Check("pass" if condition else ("fail" if required else "warn"), name, ok_detail if condition else fail_detail))


def main():
    parser = argparse.ArgumentParser(description="Check LAESim space-demo delivery prerequisites without changing the system.")
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--mission", type=Path)
    parser.add_argument("--require-ros", action="store_true")
    parser.add_argument("--require-ns3", action="store_true")
    parser.add_argument("--live", action="store_true", help="Require a running ROS/AirSim/space-demo stack.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.live:
        args.require_ros = True

    checks = []
    add(checks, sys.version_info >= (3, 8), "python", platform.python_version(), "Python 3.8 or newer is required")
    required_files = [
        ROOT / "Multi_use" / "space_mission_bridge.py",
        ROOT / "ros" / "src" / "example" / "space_constellation_bridge_ros.py",
        ROOT / "NetworkSim" / "python" / "ros_network_bridge.py",
        ROOT / "NetworkSim" / "scripts" / "start_space_demo.sh",
        ROOT / "NetworkSim" / "tests" / "ros_space_delivery_acceptance.sh",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required_files if not path.is_file()]
    add(checks, not missing, "delivery_files", "Required delivery files are present", "Missing: " + ", ".join(missing))
    add(
        checks,
        importlib.util.find_spec("sgp4") is not None,
        "sgp4",
        "Python sgp4 module is available",
        "Install sgp4 in the runtime environment",
    )
    for module in ("orekit", "Basilisk"):
        available = importlib.util.find_spec(module) is not None
        add(checks, available, module.lower(), f"Optional {module} backend is available", f"Optional {module} backend is not installed", required=False)

    settings = (args.settings or find_settings())
    if settings is None:
        checks.append(Check("fail", "settings", "AirSim settings.json was not found; pass --settings"))
        settings_data = None
    else:
        settings = settings.expanduser().resolve()
        validation = validate_files(
            settings_path=settings,
            mission_path=args.mission,
            expected_satellites=("Satellite", "Satellite2", "Satellite3"),
            expected_targets=("UAV", "UAV2", "Car", "Boat"),
            require_ns3=args.require_ns3,
        )
        add(
            checks,
            validation.error_count == 0,
            "configuration",
            f"Configuration is valid ({settings})",
            f"Configuration has {validation.error_count} error(s): " + "; ".join(
                item.message for item in validation.findings if item.level == "error"
            ),
        )
        try:
            settings_data = json.loads(settings.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            settings_data = None

    ros_setup = Path("/opt/ros/noetic/setup.bash")
    ros_devel = ROOT / "ros" / "devel" / "setup.bash"
    if args.require_ros:
        add(checks, ros_setup.is_file(), "ros_noetic", str(ros_setup), "ROS Noetic setup.bash is missing")
        add(checks, ros_devel.is_file(), "ros_workspace", str(ros_devel), "LAESim ROS workspace is not built")

    if args.require_ns3:
        runner_value = "~/opt/ns-3.48/build/scratch/ns3.48-laesim-ns3-runner"
        if settings_data:
            runner_value = settings_data.get("NetworkSimulation", {}).get("RunnerPath", runner_value)
        runner = Path(os.path.expanduser(str(runner_value)))
        add(checks, runner.is_file() and os.access(runner, os.X_OK), "ns3_runner", str(runner), f"ns-3 runner is missing or not executable: {runner}")

    if args.live:
        rosnode = shutil.which("rosnode")
        rostopic = shutil.which("rostopic")
        add(checks, bool(rosnode and rostopic), "ros_commands", "rosnode and rostopic are in PATH", "Source ROS Noetic and ros/devel/setup.bash")
        if rosnode and rostopic:
            try:
                nodes_result = run([rosnode, "list"])
                nodes = set(nodes_result.stdout.split()) if nodes_result.returncode == 0 else set()
                add(checks, nodes_result.returncode == 0, "ros_master", "ROS master is reachable", nodes_result.stderr.strip() or "ROS master is unavailable")
                add(checks, "/airsim_node" in nodes, "airsim_node", "/airsim_node is registered", "Enter UE Play and restart the AirSim ROS wrapper")
                topics_result = run([rostopic, "list"])
                topics = set(topics_result.stdout.split()) if topics_result.returncode == 0 else set()
                add(checks, "/space/Satellite/state" in topics, "space_state", "Satellite state topic is active", "Constellation bridge is not publishing Satellite state")
                add(checks, "/space/selection/Car" in topics, "space_selection", "Car selection topic is active", "Constellation selection topic is missing")
                add(checks, "/network_sim/rx/Car" in topics, "network_bridge", "NetworkSim receive topic is active", "NetworkSim bridge is not publishing Car rx")
                add(checks, "/space/visualization/status" in topics, "visualization", "UE visualization status is active", "UE visualizer status is missing", required=False)
                clock_probe = ROOT / "NetworkSim" / "tests" / "ros_ue_clock_progress_test.py"
                clock_result = run([
                    sys.executable,
                    str(clock_probe),
                    "--vehicle", "Satellite",
                    "--timeout", "3",
                ], timeout=8.0)
                add(
                    checks,
                    clock_result.returncode == 0,
                    "ue_clock_progress",
                    "Satellite ROS timestamp is advancing",
                    clock_result.stderr.strip() or clock_result.stdout.strip() or "Satellite timestamp is frozen",
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                checks.append(Check("fail", "live_probe", str(error)))

    result = {
        "passed": not any(check.status == "fail" for check in checks),
        "project_root": str(ROOT),
        "platform": platform.platform(),
        "checks": [asdict(check) for check in checks],
    }
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json:
        print(output)
    else:
        for check in checks:
            print(f"{check.status.upper():5s} {check.name}: {check.detail}")
        print("Space demo doctor: " + ("PASS" if result["passed"] else "FAIL"))
    if args.output:
        path = args.output.expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output + "\n", encoding="utf-8")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
