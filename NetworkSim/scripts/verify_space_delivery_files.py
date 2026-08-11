#!/usr/bin/env python3
"""Verify key LAESim space-delivery files and optionally write checksums."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "NetworkSim" / "config" / "space-delivery-manifest.json"


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(root, manifest_path):
    with manifest_path.open("r", encoding="utf-8-sig") as handle:
        manifest = json.load(handle)
    required = manifest.get("required_paths", [])
    if not isinstance(required, list) or not required:
        raise ValueError("manifest required_paths must be a non-empty array")

    entries = []
    missing = []
    for relative in required:
        path = root / relative
        if not path.exists():
            missing.append(relative)
            entries.append({"path": relative, "type": "missing", "sha256": ""})
        elif path.is_file():
            entries.append({
                "path": relative,
                "type": "file",
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
        elif path.is_dir():
            files = sorted(item for item in path.rglob("*") if item.is_file())
            directory_digest = hashlib.sha256()
            total_size = 0
            for item in files:
                relative_item = item.relative_to(root).as_posix()
                file_digest = sha256_file(item)
                total_size += item.stat().st_size
                directory_digest.update(relative_item.encode("utf-8"))
                directory_digest.update(file_digest.encode("ascii"))
            entries.append({
                "path": relative,
                "type": "directory",
                "file_count": len(files),
                "size_bytes": total_size,
                "sha256": directory_digest.hexdigest(),
            })
        else:
            missing.append(relative)
            entries.append({"path": relative, "type": "unsupported", "sha256": ""})
    return {
        "passed": not missing,
        "manifest": str(manifest_path),
        "project_root": str(root),
        "required_count": len(required),
        "verified_count": len(required) - len(missing),
        "missing": missing,
        "entries": entries,
    }


def main():
    parser = argparse.ArgumentParser(description="Verify the LAESim space-delivery source tree without modifying it.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    manifest = args.manifest.expanduser().resolve()
    report = verify(root, manifest)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json:
        print(output)
    else:
        print(
            f"Space delivery files: {report['verified_count']}/{report['required_count']} verified"
        )
        for path in report["missing"]:
            print(f"MISSING {path}")
        print("Verification: " + ("PASS" if report["passed"] else "FAIL"))
    if args.output:
        path = args.output.expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output + "\n", encoding="utf-8")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
