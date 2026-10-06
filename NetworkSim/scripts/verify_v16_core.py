#!/usr/bin/env python3
"""Verify inherited portable checks and the RadioMapNav CPU test suite."""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "Examples" / "RadioMapNav" / "WirelessCityFactory"


def main() -> int:
    subprocess.run(
        [sys.executable, str(ROOT / "NetworkSim/scripts/verify_v15_core.py")],
        cwd=ROOT,
        check=True,
    )
    subprocess.run([sys.executable, "-m", "pytest"], cwd=DEMO, check=True)
    print("\nV1.6 CORE VERIFICATION: PASS", flush=True)
    print("GPU ray tracing and UE flight require separate runtime acceptance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
