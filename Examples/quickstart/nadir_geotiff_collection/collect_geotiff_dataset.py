from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from coverage_mission import (
    MissionConfig,
    build_coverage_route,
    datetime_to_unix_ns,
    default_tif_path,
    draw_route_preview,
    load_geotiff_reference,
    write_mission_summary,
    write_ideal_groundtruth_csv,
    write_planned_trajectory_csv,
)


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Generate a nadir-image dataset from a georeferenced TIFF coverage mission."
    )
    parser.add_argument("--tif", type=Path, default=default_tif_path())
    parser.add_argument("--output", type=Path, default=script_dir / "output" / "geotiff_dataset")
    parser.add_argument("--distance-m", type=float, default=1000.0)
    parser.add_argument("--speed-mps", type=float, default=4.6)
    parser.add_argument("--altitude-m", type=float, default=35.0)
    parser.add_argument("--duration-s", type=float, default=218.0)
    parser.add_argument("--rate-hz", type=float, default=10.0)
    parser.add_argument("--fov-deg", type=float, default=90.0)
    parser.add_argument("--lanes", type=int, default=5)
    parser.add_argument("--cross-track-overlap", type=float, default=0.10)
    parser.add_argument("--turn-segments", type=int, default=12)
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--jpeg-quality", type=int, default=95)
    parser.add_argument(
        "--start-time-utc",
        default=None,
        help="ISO-8601 start time. Defaults to the current UTC time.",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Only write route preview, trajectory, and summary; do not create image frames.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output directory.",
    )
    return parser.parse_args()


def parse_start_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def prepare_output_directory(output_dir: Path, overwrite: bool) -> None:
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"output directory is not empty: {output_dir}; use --overwrite to replace it"
            )
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def crop_nadir_frame(
    source: Image.Image,
    pixel_bounds: tuple[float, float, float, float],
    output_size_px: int,
) -> Image.Image:
    left = int(round(pixel_bounds[0]))
    top = int(round(pixel_bounds[1]))
    right = int(round(pixel_bounds[2]))
    bottom = int(round(pixel_bounds[3]))
    if left < 0 or top < 0 or right > source.width or bottom > source.height:
        raise ValueError(f"camera footprint leaves GeoTIFF: {(left, top, right, bottom)}")
    frame = source.crop((left, top, right, bottom))
    if frame.size != (output_size_px, output_size_px):
        frame = frame.resize((output_size_px, output_size_px), Image.Resampling.LANCZOS)
    return frame


def collect_dataset(args: argparse.Namespace) -> Path:
    if args.image_size < 32:
        raise ValueError("--image-size must be at least 32")
    if not 1 <= args.jpeg_quality <= 100:
        raise ValueError("--jpeg-quality must be in [1, 100]")

    output_dir = args.output.expanduser().resolve()
    prepare_output_directory(output_dir, args.overwrite)
    reference = load_geotiff_reference(args.tif)
    config = MissionConfig(
        distance_m=args.distance_m,
        speed_mps=args.speed_mps,
        altitude_m=args.altitude_m,
        duration_s=args.duration_s,
        rate_hz=args.rate_hz,
        horizontal_fov_deg=args.fov_deg,
        lane_count=args.lanes,
        cross_track_overlap=args.cross_track_overlap,
        turn_segments=args.turn_segments,
    )
    route = build_coverage_route(reference, config)
    start_time = parse_start_time(args.start_time_utc)
    start_time_ns = datetime_to_unix_ns(start_time)

    preview_path = output_dir / "route_preview.jpg"
    trajectory_path = output_dir / "planned_trajectory.csv"
    groundtruth_path = output_dir / "groundtruth.csv"
    summary_path = output_dir / "mission_summary.json"
    draw_route_preview(route, preview_path)
    write_planned_trajectory_csv(route, trajectory_path)
    write_ideal_groundtruth_csv(route, groundtruth_path, start_time)

    collection_info = {
        "collection": {
            "backend": "geotiff",
            "plan_only": bool(args.plan_only),
            "start_time_utc": start_time.isoformat().replace("+00:00", "Z"),
            "image_size_px": args.image_size,
            "jpeg_quality": args.jpeg_quality,
            "image_count": 0 if args.plan_only else config.frame_count,
        }
    }
    write_mission_summary(route, summary_path, collection_info)

    if args.plan_only:
        print(f"Plan written to: {output_dir}")
        return output_dir

    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = output_dir / "metadata.csv"
    fieldnames = [
        "frame_index",
        "scheduled_time_s",
        "timestamp_utc",
        "timestamp_unix_ns",
        "image_file",
        "longitude_deg",
        "latitude_deg",
        "altitude_m",
        "local_north_m",
        "local_east_m",
        "local_down_m",
        "projected_x_m",
        "projected_y_m",
        "source_column_px",
        "source_row_px",
        "path_distance_m",
        "commanded_speed_mps",
        "is_holding",
        "segment_index",
    ]

    with Image.open(reference.path) as source_image:
        source = source_image.convert("RGB")
    with metadata_path.open("w", newline="", encoding="utf-8") as metadata_stream:
        writer = csv.DictWriter(metadata_stream, fieldnames=fieldnames)
        writer.writeheader()
        for sample in route.samples():
            center_column_px, center_row_px = reference.projected_to_pixel(
                sample.projected_x_m, sample.projected_y_m
            )
            frame = crop_nadir_frame(
                source,
                reference.local_footprint_pixel_bounds(
                    sample.local_east_m,
                    sample.local_north_m,
                    config.footprint_width_m,
                ),
                args.image_size,
            )
            image_name = f"frame_{sample.frame_index:06d}.jpg"
            relative_image_path = Path("images") / image_name
            frame.save(
                output_dir / relative_image_path,
                format="JPEG",
                quality=args.jpeg_quality,
                subsampling=0,
                optimize=False,
            )
            timestamp = start_time + timedelta(seconds=sample.scheduled_time_s)
            writer.writerow(
                {
                    "frame_index": sample.frame_index,
                    "scheduled_time_s": f"{sample.scheduled_time_s:.3f}",
                    "timestamp_utc": timestamp.isoformat(timespec="milliseconds").replace(
                        "+00:00", "Z"
                    ),
                    "timestamp_unix_ns": start_time_ns
                    + int(round(sample.scheduled_time_s * 1_000_000_000)),
                    "image_file": relative_image_path.as_posix(),
                    "longitude_deg": f"{sample.longitude_deg:.10f}",
                    "latitude_deg": f"{sample.latitude_deg:.10f}",
                    "altitude_m": f"{config.altitude_m:.3f}",
                    "local_north_m": f"{sample.local_north_m:.6f}",
                    "local_east_m": f"{sample.local_east_m:.6f}",
                    "local_down_m": f"{sample.local_down_m:.6f}",
                    "projected_x_m": f"{sample.projected_x_m:.6f}",
                    "projected_y_m": f"{sample.projected_y_m:.6f}",
                    "source_column_px": f"{center_column_px:.3f}",
                    "source_row_px": f"{center_row_px:.3f}",
                    "path_distance_m": f"{sample.path_distance_m:.6f}",
                    "commanded_speed_mps": f"{sample.commanded_speed_mps:.3f}",
                    "is_holding": int(sample.is_holding),
                    "segment_index": sample.segment_index,
                }
            )
            if (sample.frame_index + 1) % 100 == 0 or sample.frame_index + 1 == config.frame_count:
                print(f"Saved {sample.frame_index + 1}/{config.frame_count} frames")

    manifest = {
        "metadata_csv": metadata_path.name,
        "planned_trajectory_csv": trajectory_path.name,
        "groundtruth_csv": groundtruth_path.name,
        "route_preview": preview_path.name,
        "summary_json": summary_path.name,
        "images_directory": image_dir.name,
        "frame_count": config.frame_count,
    }
    (output_dir / "dataset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Dataset written to: {output_dir}")
    return output_dir


def main() -> None:
    args = parse_args()
    collect_dataset(args)


if __name__ == "__main__":
    main()
