"""Command-line entry point for wireless-city."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import MORPHOLOGIES, load_config
from .pipeline import PipelineError, generate, generate_candidates
from .profiles import CITY_PROFILE_NAMES
from .ue import validate_ue_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wireless-city", description="Generate deterministic wireless city digital twins.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate_parser = subparsers.add_parser("generate", help="Run city and selected optional stages.")
    generate_parser.add_argument("--config", required=True, type=Path)
    generate_parser.add_argument("--project-root", type=Path, default=None)
    candidates_parser = subparsers.add_parser(
        "generate-candidates",
        help="Generate a city-only morphology and seed matrix.",
    )
    candidates_parser.add_argument("--config", required=True, type=Path)
    candidates_parser.add_argument("--project-root", type=Path, default=None)
    variants = candidates_parser.add_mutually_exclusive_group()
    variants.add_argument("--morphologies", nargs="+", choices=MORPHOLOGIES)
    variants.add_argument("--city-profiles", nargs="+", choices=CITY_PROFILE_NAMES)
    candidates_parser.add_argument("--seeds", nargs="+", type=int, required=True)
    candidates_parser.add_argument("--site-densities", nargs="+", type=float, default=None)
    validate_parser = subparsers.add_parser("validate-ue", help="Validate a generated UE bundle without Unreal.")
    validate_parser.add_argument("bundle", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "generate":
            config = load_config(args.config)
            result = generate(config, project_root=args.project_root)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "generate-candidates":
            config = load_config(args.config)
            result = generate_candidates(
                config,
                morphologies=(
                    args.morphologies
                    if args.morphologies is not None
                    else (None if args.city_profiles else list(MORPHOLOGIES))
                ),
                city_profiles=args.city_profiles,
                seeds=args.seeds,
                site_densities_per_km2=args.site_densities,
                project_root=args.project_root,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "validate-ue":
            result = validate_ue_bundle(args.bundle)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        return 2
    except (PipelineError, TypeError, ValueError, RuntimeError, OSError) as exc:
        print(f"wireless-city failed: {exc}", file=sys.stderr)
        return 2
