"""Print a compact summary for a generated run without optional dependencies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    scene = json.loads((args.run / "scene.json").read_text(encoding="utf-8"))
    print(json.dumps({"scene_id": scene["scene_id"], "scene_fingerprint": scene["metadata"].get("scene_fingerprint"), "roads": len(scene["roads"]), "blocks": len(scene["blocks"]), "buildings": len(scene["buildings"]), "base_stations": len(scene["base_stations"]), "tasks": len(scene["tasks"])}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

