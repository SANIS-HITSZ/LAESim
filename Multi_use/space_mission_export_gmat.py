#!/usr/bin/env python3
"""Export a LAESim space mission handoff package for GMAT-style offline design.

The generated script is a starting point for mission design, not a bit-exact
round trip from LAESim. LAESim remains the runtime visualization and ROS bridge;
GMAT is treated as an offline design tool.
"""

import argparse
import json
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MULTI_USE = os.path.join(ROOT, "Multi_use")
if MULTI_USE not in sys.path:
    sys.path.insert(0, MULTI_USE)

import space_mission_analyzer as analyzer


def parse_args():
    parser = argparse.ArgumentParser(description="Export a GMAT handoff package from a LAESim space mission JSON.")
    parser.add_argument("--mission", default=os.path.join(ROOT, "Multi_use", "space_mission.example.json"))
    parser.add_argument("--out", default=os.path.join(ROOT, "Multi_use", "space_mission_gmat.script"))
    return parser.parse_args()


def write_gmat_script(config, result, path):
    satellites = config.get("satellites", [])
    constellations = config.get("constellations", [])
    analysis = config.get("analysis", {})
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("% LAESim GMAT handoff script\n")
        handle.write("% Generated from space_mission_export_gmat.py\n")
        handle.write("% Use this as an offline mission-design starting point.\n\n")
        handle.write("Create ForceModel EarthPointMass;\n")
        handle.write("EarthPointMass.CentralBody = Earth;\n")
        handle.write("EarthPointMass.PrimaryBodies = {Earth};\n\n")
        handle.write("Create Propagator DefaultProp;\n")
        handle.write("DefaultProp.FM = EarthPointMass;\n")
        handle.write("DefaultProp.Type = RungeKutta89;\n")
        handle.write("DefaultProp.InitialStepSize = 60;\n\n")

        created = []
        for index, sat in enumerate(satellites, start=1):
            name = sat.get("name", f"Satellite{index}")
            created.append(name)
            handle.write(f"Create Spacecraft {name};\n")
            handle.write(f"% LAESim provider: {sat.get('provider', 'unknown')}\n")
            if sat.get("tle"):
                handle.write(f"% Source TLE: {sat.get('tle')}\n")
            handle.write(f"{name}.DateFormat = UTCGregorian;\n")
            handle.write(f"{name}.Epoch = '{analysis.get('start_time', '2026-07-23T00:00:00Z').replace('T', ' ').replace('Z', '')}.000';\n")
            handle.write(f"{name}.CoordinateSystem = EarthMJ2000Eq;\n")
            handle.write(f"{name}.DisplayStateType = Cartesian;\n")
            handle.write(f"% TODO: Replace placeholder Cartesian state with a GMAT-designed orbit or imported ephemeris.\n")
            handle.write(f"{name}.X = {7000 + index * 10};\n{name}.Y = 0;\n{name}.Z = 0;\n")
            handle.write(f"{name}.VX = 0;\n{name}.VY = 7.5;\n{name}.VZ = 0;\n\n")

        for constellation in constellations:
            handle.write(f"% Constellation handoff: {json.dumps(constellation, ensure_ascii=False)}\n")

        handle.write("BeginMissionSequence;\n")
        for name in created:
            handle.write(f"Propagate DefaultProp({name}) {{{name}.ElapsedSecs = {float(analysis.get('duration_s', 3600.0))}}};\n")
        handle.write("\n% LAESim analysis summary follows.\n")
        handle.write("% target_groups = " + json.dumps(result["summary"].get("target_groups", {}), ensure_ascii=False) + "\n")


def main():
    args = parse_args()
    config = analyzer.load_json(args.mission)
    result = analyzer.analyze(args.mission)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    write_gmat_script(config, result, args.out)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
