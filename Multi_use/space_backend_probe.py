#!/usr/bin/env python3
"""Probe optional professional space backends for LAESim."""

import importlib.util
import json
import shutil


def has_module(name):
    return importlib.util.find_spec(name) is not None


def main():
    report = {
        "sgp4": {
            "available": has_module("sgp4"),
            "purpose": "TLE/SGP4 propagation used by the default LAESim space bridge",
        },
        "orekit": {
            "available": has_module("orekit"),
            "purpose": "optional high-precision propagation, frames, time systems, and event detection",
        },
        "gmat": {
            "available": shutil.which("GMAT") is not None or shutil.which("GMAT.exe") is not None,
            "purpose": "offline mission design; LAESim exports a handoff script",
        },
        "basilisk": {
            "available": has_module("Basilisk") or has_module("basilisk"),
            "purpose": "optional spacecraft attitude and dynamics simulation; LAESim can ingest exported attitude CSV",
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
