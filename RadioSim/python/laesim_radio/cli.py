"""Build a radio map for an existing LAESim scene snapshot."""

import argparse
import json
from pathlib import Path

from laesim_scene.config import load_config
from laesim_scene.repository import repository_root

from .build import build_radio_map
from .runtime import RadioMapLookup


def main(argv=None) -> int:
    repository_root()
    parser = argparse.ArgumentParser(prog="laesim-radio")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Compute a radio map without regenerating scene geometry.")
    build.add_argument("--scene-run", type=Path, required=True)
    build.add_argument("--config", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True, help="New radio snapshot directory; source is never overwritten.")
    query = commands.add_parser("query", help="Query an existing map in scene metres (+Z up).")
    query.add_argument("--run-dir", type=Path, required=True)
    query.add_argument("--position", type=float, nargs=3, required=True)
    args = parser.parse_args(argv)
    if args.command == "build":
        config = load_config(args.config)
        if not config.radio.enabled:
            parser.error("Radio calculation must be enabled in the configuration.")
        result = build_radio_map(args.scene_run, config, args.output)
    else:
        result = RadioMapLookup.load(args.run_dir).query(tuple(args.position)).to_dict()
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0
