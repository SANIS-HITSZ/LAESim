#!/usr/bin/env python3
"""Run the portable LAESim V1.5 checks that do not require UE, ROS, or ns-3."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_step(name: str, command: list[str]) -> None:
    print(f"\n== {name} ==", flush=True)
    print("$ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def validate_json_files() -> int:
    roots = (
        ROOT / "Examples" / "quickstart",
        ROOT / "how_to_use_settings",
        ROOT / "NetworkSim" / "config",
        ROOT / "Multi_use",
    )
    paths = sorted(
        path
        for directory in roots
        for path in directory.rglob("*.json")
        if path.is_file()
    )
    if not paths:
        raise RuntimeError("no V1.5 JSON configuration files were found")
    for path in paths:
        with path.open("r", encoding="utf-8-sig") as stream:
            json.load(stream)
    print(f"JSON configuration files: {len(paths)}/{len(paths)} valid")
    return len(paths)


def compile_python_files() -> int:
    patterns = (
        "Examples/quickstart/**/*.py",
        "Multi_use/space_*.py",
        "Multi_use/update_tle.py",
        "NetworkSim/python/*.py",
        "NetworkSim/scripts/*.py",
        "NetworkSim/tests/*.py",
    )
    paths = sorted(
        {
            path
            for pattern in patterns
            for path in ROOT.glob(pattern)
            if path.is_file()
        }
    )
    if not paths:
        raise RuntimeError("no V1.5 Python files were found")
    for path in paths:
        source = path.read_text(encoding="utf-8-sig")
        compile(source, str(path), "exec")
    print(f"Python syntax files: {len(paths)}/{len(paths)} compiled")
    return len(paths)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the portable V1.5 source tree, JSON settings, Python syntax, "
            "quickstart configuration, deterministic unit tests, and direct backend."
        )
    )
    parser.parse_args()

    print(f"LAESim root: {ROOT}")
    print(f"Python: {sys.version.split()[0]}")
    run_step(
        "Portable source manifest",
        [sys.executable, "NetworkSim/scripts/verify_space_delivery_files.py"],
    )

    print("\n== JSON configuration parsing ==")
    json_count = validate_json_files()

    print("\n== Python syntax compilation ==")
    python_count = compile_python_files()

    run_step(
        "Heterogeneous quickstart configuration",
        [
            sys.executable,
            "Examples/quickstart/heterogeneous_fleet/run_experiment.py",
            "--settings",
            "Examples/quickstart/heterogeneous_fleet/settings.json",
            "--check-only",
        ],
    )
    run_step(
        "NetworkSim deterministic unit tests",
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "NetworkSim/tests",
            "-p",
            "test_*.py",
            "-v",
        ],
    )
    run_step(
        "Direct network backend smoke test",
        [sys.executable, "NetworkSim/tests/smoke_backend.py"],
    )

    print("\nV1.5 CORE VERIFICATION: PASS")
    print(f"Validated {json_count} JSON files and compiled {python_count} Python files.")
    print("The UE, ROS, and real ns-3 runtime checks are separate acceptance layers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
