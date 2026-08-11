#!/usr/bin/env python3
"""Download and validate one current TLE for LAESim mission demos."""

import argparse
import datetime as dt
import json
import os
import tempfile
import urllib.parse
import urllib.request

import space_mission_bridge as bridge


DEFAULT_URL = "https://celestrak.org/NORAD/elements/gp.php"


def tle_checksum(line):
    return sum(int(char) if char.isdigit() else 1 if char == "-" else 0 for char in line[:68]) % 10


def validate_tle_line(line, prefix):
    if not line.startswith(prefix) or len(line) < 69:
        raise RuntimeError(f"Invalid TLE line {prefix.strip()}: {line!r}")
    if not line[68].isdigit() or tle_checksum(line) != int(line[68]):
        raise RuntimeError(f"TLE checksum failed for line {prefix.strip()}")


def parse_tle(text):
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if line.startswith("1 ") and index + 1 < len(lines) and lines[index + 1].startswith("2 "):
            name = lines[index - 1].strip() if index > 0 and not lines[index - 1].startswith(("1 ", "2 ")) else "SATELLITE"
            line1 = line
            line2 = lines[index + 1]
            validate_tle_line(line1, "1 ")
            validate_tle_line(line2, "2 ")
            return name, line1, line2
    raise RuntimeError("The response did not contain a complete TLE")


def write_atomic(path, content):
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(prefix=".tle-", dir=os.path.dirname(path), text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def main():
    parser = argparse.ArgumentParser(description="Download a current TLE from CelesTrak.")
    parser.add_argument("--catalog-number", type=int, default=25544)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metadata", default="")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    query = urllib.parse.urlencode({"CATNR": args.catalog_number, "FORMAT": "TLE"})
    url = f"{args.url}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "LAESim-space-mission-bridge/1.0"})
    with urllib.request.urlopen(request, timeout=args.timeout) as response:
        text = response.read().decode("utf-8-sig")

    name, line1, line2 = parse_tle(text)
    epoch = bridge.tle_epoch_from_line1(line1)
    content = f"{name}\n{line1}\n{line2}\n"
    write_atomic(args.output, content)

    metadata_path = args.metadata or f"{os.path.abspath(args.output)}.json"
    metadata = {
        "name": name,
        "catalog_number": args.catalog_number,
        "source_url": url,
        "fetched_at": bridge.format_time(dt.datetime.now(dt.timezone.utc)),
        "tle_epoch": bridge.format_time(epoch),
        "output": os.path.abspath(args.output),
    }
    write_atomic(metadata_path, json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
