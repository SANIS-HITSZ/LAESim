from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw
from pyproj import CRS, Transformer


MODEL_PIXEL_SCALE_TAG = 33550
MODEL_TIEPOINT_TAG = 33922
GEO_KEY_DIRECTORY_TAG = 34735
GEO_ASCII_PARAMS_TAG = 34737


@dataclass
class GeoTiffReference:
    path: Path
    width_px: int
    height_px: int
    pixel_size_x_m: float
    pixel_size_y_m: float
    upper_left_x_m: float
    upper_left_y_m: float
    crs: CRS
    crs_description: str
    _to_wgs84: Transformer = field(init=False, repr=False)
    _local_crs: CRS = field(init=False, repr=False)
    _local_to_projected: Transformer = field(init=False, repr=False)
    _projected_to_local: Transformer = field(init=False, repr=False)
    _local_to_wgs84: Transformer = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._to_wgs84 = Transformer.from_crs(self.crs, CRS.from_epsg(4326), always_xy=True)
        center_lon, center_lat = self._to_wgs84.transform(self.center_x_m, self.center_y_m)
        self._local_crs = CRS.from_proj4(
            f"+proj=aeqd +lat_0={center_lat:.15f} +lon_0={center_lon:.15f} "
            "+datum=WGS84 +units=m +no_defs"
        )
        self._local_to_projected = Transformer.from_crs(
            self._local_crs, self.crs, always_xy=True
        )
        self._projected_to_local = Transformer.from_crs(
            self.crs, self._local_crs, always_xy=True
        )
        self._local_to_wgs84 = Transformer.from_crs(
            self._local_crs, CRS.from_epsg(4326), always_xy=True
        )

    @property
    def lower_right_x_m(self) -> float:
        return self.upper_left_x_m + self.width_px * self.pixel_size_x_m

    @property
    def lower_right_y_m(self) -> float:
        return self.upper_left_y_m - self.height_px * self.pixel_size_y_m

    @property
    def center_x_m(self) -> float:
        return 0.5 * (self.upper_left_x_m + self.lower_right_x_m)

    @property
    def center_y_m(self) -> float:
        return 0.5 * (self.upper_left_y_m + self.lower_right_y_m)

    @property
    def width_m(self) -> float:
        return self.width_px * self.pixel_size_x_m

    @property
    def height_m(self) -> float:
        return self.height_px * self.pixel_size_y_m

    @property
    def ground_width_m(self) -> float:
        west_east, _ = self.projected_to_local(
            self.upper_left_x_m, self.center_y_m
        )
        east_east, _ = self.projected_to_local(
            self.lower_right_x_m, self.center_y_m
        )
        return east_east - west_east

    @property
    def ground_height_m(self) -> float:
        _, south_north = self.projected_to_local(
            self.center_x_m, self.lower_right_y_m
        )
        _, north_north = self.projected_to_local(
            self.center_x_m, self.upper_left_y_m
        )
        return north_north - south_north

    def pixel_to_projected(self, column_px: float, row_px: float) -> tuple[float, float]:
        x_m = self.upper_left_x_m + column_px * self.pixel_size_x_m
        y_m = self.upper_left_y_m - row_px * self.pixel_size_y_m
        return x_m, y_m

    def projected_to_pixel(self, x_m: float, y_m: float) -> tuple[float, float]:
        column_px = (x_m - self.upper_left_x_m) / self.pixel_size_x_m
        row_px = (self.upper_left_y_m - y_m) / self.pixel_size_y_m
        return column_px, row_px

    def projected_to_lon_lat(self, x_m: float, y_m: float) -> tuple[float, float]:
        longitude_deg, latitude_deg = self._to_wgs84.transform(x_m, y_m)
        return float(longitude_deg), float(latitude_deg)

    def local_to_projected(self, east_m: float, north_m: float) -> tuple[float, float]:
        x_m, y_m = self._local_to_projected.transform(east_m, north_m)
        return float(x_m), float(y_m)

    def projected_to_local(self, x_m: float, y_m: float) -> tuple[float, float]:
        east_m, north_m = self._projected_to_local.transform(x_m, y_m)
        return float(east_m), float(north_m)

    def local_to_lon_lat(self, east_m: float, north_m: float) -> tuple[float, float]:
        longitude_deg, latitude_deg = self._local_to_wgs84.transform(east_m, north_m)
        return float(longitude_deg), float(latitude_deg)

    def local_footprint_pixel_bounds(
        self,
        center_east_m: float,
        center_north_m: float,
        footprint_width_m: float,
    ) -> tuple[float, float, float, float]:
        half_width_m = 0.5 * footprint_width_m
        pixel_corners = []
        for east_offset_m, north_offset_m in (
            (-half_width_m, -half_width_m),
            (-half_width_m, half_width_m),
            (half_width_m, -half_width_m),
            (half_width_m, half_width_m),
        ):
            x_m, y_m = self.local_to_projected(
                center_east_m + east_offset_m,
                center_north_m + north_offset_m,
            )
            pixel_corners.append(self.projected_to_pixel(x_m, y_m))
        columns = [point[0] for point in pixel_corners]
        rows = [point[1] for point in pixel_corners]
        return min(columns), min(rows), max(columns), max(rows)

    def center_lon_lat(self) -> tuple[float, float]:
        return self.projected_to_lon_lat(self.center_x_m, self.center_y_m)

    def to_dict(self) -> dict:
        northwest_lon, northwest_lat = self.projected_to_lon_lat(
            self.upper_left_x_m, self.upper_left_y_m
        )
        southeast_lon, southeast_lat = self.projected_to_lon_lat(
            self.lower_right_x_m, self.lower_right_y_m
        )
        center_lon, center_lat = self.center_lon_lat()
        return {
            "path": str(self.path),
            "width_px": self.width_px,
            "height_px": self.height_px,
            "pixel_size_x_m": self.pixel_size_x_m,
            "pixel_size_y_m": self.pixel_size_y_m,
            "projected_width_m": self.width_m,
            "projected_height_m": self.height_m,
            "approx_ground_width_m": self.ground_width_m,
            "approx_ground_height_m": self.ground_height_m,
            "crs": self.crs.to_string(),
            "crs_description": self.crs_description,
            "bounds_projected_m": {
                "west": self.upper_left_x_m,
                "north": self.upper_left_y_m,
                "east": self.lower_right_x_m,
                "south": self.lower_right_y_m,
            },
            "bounds_wgs84_deg": {
                "west": northwest_lon,
                "north": northwest_lat,
                "east": southeast_lon,
                "south": southeast_lat,
            },
            "center_wgs84_deg": {
                "longitude": center_lon,
                "latitude": center_lat,
            },
        }


@dataclass(frozen=True)
class MissionConfig:
    distance_m: float = 1000.0
    speed_mps: float = 4.6
    altitude_m: float = 35.0
    duration_s: float = 218.0
    rate_hz: float = 10.0
    horizontal_fov_deg: float = 90.0
    lane_count: int = 5
    cross_track_overlap: float = 0.10
    turn_segments: int = 12

    @property
    def moving_duration_s(self) -> float:
        return self.distance_m / self.speed_mps

    @property
    def hold_duration_s(self) -> float:
        return max(0.0, self.duration_s - self.moving_duration_s)

    @property
    def nominal_distance_from_speed_and_time_m(self) -> float:
        return self.speed_mps * self.duration_s

    @property
    def footprint_width_m(self) -> float:
        half_angle_rad = math.radians(self.horizontal_fov_deg * 0.5)
        return 2.0 * self.altitude_m * math.tan(half_angle_rad)

    @property
    def lane_spacing_m(self) -> float:
        return self.footprint_width_m * (1.0 - self.cross_track_overlap)

    @property
    def frame_count(self) -> int:
        intervals = self.duration_s * self.rate_hz
        rounded = round(intervals)
        if not math.isclose(intervals, rounded, abs_tol=1e-9):
            raise ValueError("duration_s * rate_hz must be an integer")
        return int(rounded) + 1

    def validate(self) -> None:
        if self.distance_m <= 0.0:
            raise ValueError("distance_m must be positive")
        if self.speed_mps <= 0.0:
            raise ValueError("speed_mps must be positive")
        if self.altitude_m <= 0.0:
            raise ValueError("altitude_m must be positive")
        if self.duration_s <= 0.0:
            raise ValueError("duration_s must be positive")
        if self.rate_hz <= 0.0:
            raise ValueError("rate_hz must be positive")
        if not 1.0 < self.horizontal_fov_deg < 179.0:
            raise ValueError("horizontal_fov_deg must be between 1 and 179 degrees")
        if self.lane_count < 2:
            raise ValueError("lane_count must be at least 2")
        if self.turn_segments < 2:
            raise ValueError("turn_segments must be at least 2")
        if not 0.0 <= self.cross_track_overlap < 1.0:
            raise ValueError("cross_track_overlap must be in [0, 1)")
        if self.duration_s + 1e-9 < self.moving_duration_s:
            raise ValueError(
                "duration_s is too short for distance_m at speed_mps; "
                f"at least {self.moving_duration_s:.3f} s is required"
            )


@dataclass(frozen=True)
class RouteSample:
    frame_index: int
    scheduled_time_s: float
    path_distance_m: float
    local_north_m: float
    local_east_m: float
    local_down_m: float
    projected_x_m: float
    projected_y_m: float
    longitude_deg: float
    latitude_deg: float
    commanded_speed_mps: float
    is_holding: bool
    segment_index: int


TRAJECTORY_FIELDNAMES = [
    "sample_index",
    "schedule_frame_index",
    "scheduled_time_s",
    "actual_elapsed_s",
    "wall_time_utc",
    "state_timestamp_ns",
    "image_timestamp_ns",
    "source",
    "position_north_m",
    "position_east_m",
    "position_down_m",
    "velocity_north_mps",
    "velocity_east_mps",
    "velocity_down_mps",
    "acceleration_north_mps2",
    "acceleration_east_mps2",
    "acceleration_down_mps2",
    "orientation_qx",
    "orientation_qy",
    "orientation_qz",
    "orientation_qw",
    "angular_velocity_x_radps",
    "angular_velocity_y_radps",
    "angular_velocity_z_radps",
    "angular_acceleration_x_radps2",
    "angular_acceleration_y_radps2",
    "angular_acceleration_z_radps2",
    "longitude_deg",
    "latitude_deg",
    "altitude_m",
]


def datetime_to_unix_ns(value: datetime) -> int:
    if value.tzinfo is None:
        raise ValueError("datetime must include timezone information")
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = value.astimezone(timezone.utc) - epoch
    return (
        (delta.days * 86400 + delta.seconds) * 1_000_000_000
        + delta.microseconds * 1000
    )


class CoverageRoute:
    def __init__(
        self,
        reference: GeoTiffReference,
        config: MissionConfig,
        local_east_north_points: Sequence[tuple[float, float]],
    ) -> None:
        if len(local_east_north_points) < 2:
            raise ValueError("route requires at least two points")
        self.reference = reference
        self.config = config
        self.local_east_north_points = tuple(local_east_north_points)
        self.segment_lengths_m: list[float] = []
        self.cumulative_distances_m: list[float] = [0.0]
        for start, end in zip(self.local_east_north_points, self.local_east_north_points[1:]):
            length = math.hypot(end[0] - start[0], end[1] - start[1])
            if length <= 0.0:
                raise ValueError("route contains a zero-length segment")
            self.segment_lengths_m.append(length)
            self.cumulative_distances_m.append(self.cumulative_distances_m[-1] + length)

    @property
    def total_length_m(self) -> float:
        return self.cumulative_distances_m[-1]

    def interpolate_local(self, distance_m: float) -> tuple[float, float, int]:
        distance_m = min(max(0.0, distance_m), self.total_length_m)
        for index, segment_end_distance in enumerate(self.cumulative_distances_m[1:]):
            if distance_m <= segment_end_distance + 1e-9:
                segment_start_distance = self.cumulative_distances_m[index]
                ratio = (distance_m - segment_start_distance) / self.segment_lengths_m[index]
                start = self.local_east_north_points[index]
                end = self.local_east_north_points[index + 1]
                east_m = start[0] + ratio * (end[0] - start[0])
                north_m = start[1] + ratio * (end[1] - start[1])
                return east_m, north_m, index
        east_m, north_m = self.local_east_north_points[-1]
        return east_m, north_m, len(self.segment_lengths_m) - 1

    def sample_at(self, frame_index: int) -> RouteSample:
        time_s = frame_index / self.config.rate_hz
        if time_s > self.config.duration_s + 1e-9:
            raise IndexError("frame_index is outside the mission duration")
        path_distance_m = min(self.config.speed_mps * time_s, self.total_length_m)
        east_m, north_m, segment_index = self.interpolate_local(path_distance_m)
        projected_x_m, projected_y_m = self.reference.local_to_projected(east_m, north_m)
        longitude_deg, latitude_deg = self.reference.local_to_lon_lat(east_m, north_m)
        is_holding = time_s >= self.config.moving_duration_s - 1e-9
        return RouteSample(
            frame_index=frame_index,
            scheduled_time_s=time_s,
            path_distance_m=path_distance_m,
            local_north_m=north_m,
            local_east_m=east_m,
            local_down_m=-self.config.altitude_m,
            projected_x_m=projected_x_m,
            projected_y_m=projected_y_m,
            longitude_deg=longitude_deg,
            latitude_deg=latitude_deg,
            commanded_speed_mps=0.0 if is_holding else self.config.speed_mps,
            is_holding=is_holding,
            segment_index=segment_index,
        )

    def samples(self) -> Iterable[RouteSample]:
        for frame_index in range(self.config.frame_count):
            yield self.sample_at(frame_index)

    def ideal_velocity_at(self, sample: RouteSample) -> tuple[float, float, float]:
        if sample.is_holding:
            return 0.0, 0.0, 0.0
        start = self.local_east_north_points[sample.segment_index]
        end = self.local_east_north_points[sample.segment_index + 1]
        segment_length_m = self.segment_lengths_m[sample.segment_index]
        east_mps = self.config.speed_mps * (end[0] - start[0]) / segment_length_m
        north_mps = self.config.speed_mps * (end[1] - start[1]) / segment_length_m
        return north_mps, east_mps, 0.0

    def to_summary(self) -> dict:
        east_values = [point[0] for point in self.local_east_north_points]
        north_values = [point[1] for point in self.local_east_north_points]
        along_track_step_m = self.config.speed_mps / self.config.rate_hz
        return {
            "mission": asdict(self.config),
            "derived": {
                "route_length_m": self.total_length_m,
                "moving_duration_s": self.config.moving_duration_s,
                "hold_duration_s": self.config.hold_duration_s,
                "nominal_distance_from_speed_and_time_m": (
                    self.config.nominal_distance_from_speed_and_time_m
                ),
                "expected_frame_count_including_t0": self.config.frame_count,
                "camera_ground_footprint_width_m": self.config.footprint_width_m,
                "lane_spacing_m": self.config.lane_spacing_m,
                "turn_radius_m": 0.5 * self.config.lane_spacing_m,
                "turn_segments_per_half_circle": self.config.turn_segments,
                "along_track_sample_spacing_m": along_track_step_m,
                "estimated_along_track_overlap": max(
                    0.0, 1.0 - along_track_step_m / self.config.footprint_width_m
                ),
                "route_local_bounds_m": {
                    "west": min(east_values),
                    "east": max(east_values),
                    "south": min(north_values),
                    "north": max(north_values),
                },
            },
            "geotiff": self.reference.to_dict(),
            "waypoints_local_ned_m": [
                {
                    "north": north_m,
                    "east": east_m,
                    "down": -self.config.altitude_m,
                }
                for east_m, north_m in self.local_east_north_points
            ],
        }


def load_geotiff_reference(path: Path | str) -> GeoTiffReference:
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    with Image.open(path) as image:
        tags = image.tag_v2
        if MODEL_PIXEL_SCALE_TAG not in tags or MODEL_TIEPOINT_TAG not in tags:
            raise ValueError(f"{path} does not contain GeoTIFF scale/tie-point tags")
        pixel_scale = tags[MODEL_PIXEL_SCALE_TAG]
        tiepoint = tags[MODEL_TIEPOINT_TAG]
        if len(pixel_scale) < 2 or len(tiepoint) < 6:
            raise ValueError(f"{path} contains incomplete GeoTIFF georeferencing tags")

        pixel_size_x_m = abs(float(pixel_scale[0]))
        pixel_size_y_m = abs(float(pixel_scale[1]))
        tie_column_px = float(tiepoint[0])
        tie_row_px = float(tiepoint[1])
        tie_x_m = float(tiepoint[3])
        tie_y_m = float(tiepoint[4])
        upper_left_x_m = tie_x_m - tie_column_px * pixel_size_x_m
        upper_left_y_m = tie_y_m + tie_row_px * pixel_size_y_m
        crs_description = str(tags.get(GEO_ASCII_PARAMS_TAG, ""))
        geo_keys = tuple(tags.get(GEO_KEY_DIRECTORY_TAG, ()))

        if "Web_Mercator" in crs_description or "Mercator_Auxiliary_Sphere" in crs_description:
            crs = CRS.from_epsg(3857)
        elif 3857 in geo_keys:
            crs = CRS.from_epsg(3857)
        else:
            raise ValueError(
                "unsupported GeoTIFF CRS; this collector currently expects WGS84 Web Mercator"
            )

        return GeoTiffReference(
            path=path,
            width_px=int(image.width),
            height_px=int(image.height),
            pixel_size_x_m=pixel_size_x_m,
            pixel_size_y_m=pixel_size_y_m,
            upper_left_x_m=upper_left_x_m,
            upper_left_y_m=upper_left_y_m,
            crs=crs,
            crs_description=crs_description,
        )


def build_coverage_route(
    reference: GeoTiffReference,
    config: MissionConfig,
) -> CoverageRoute:
    config.validate()
    turn_radius_m = 0.5 * config.lane_spacing_m
    turn_chord_length_m = 2.0 * turn_radius_m * math.sin(
        math.pi / (2.0 * config.turn_segments)
    )
    one_turn_length_m = config.turn_segments * turn_chord_length_m
    total_turn_length_m = (config.lane_count - 1) * one_turn_length_m
    remaining_scan_distance_m = config.distance_m - total_turn_length_m
    if remaining_scan_distance_m <= 0.0:
        raise ValueError(
            "distance_m is too short for the requested lane count, footprint, and overlap"
        )
    scan_length_m = remaining_scan_distance_m / config.lane_count
    half_scan_m = 0.5 * scan_length_m
    first_north_m = -0.5 * (config.lane_count - 1) * config.lane_spacing_m

    points: list[tuple[float, float]] = [(-half_scan_m, first_north_m)]
    for lane_index in range(config.lane_count):
        north_m = first_north_m + lane_index * config.lane_spacing_m
        direction = 1.0 if lane_index % 2 == 0 else -1.0
        end_east_m = half_scan_m * direction
        points.append((end_east_m, north_m))
        if lane_index + 1 < config.lane_count:
            center_north_m = north_m + turn_radius_m
            angle_start = -0.5 * math.pi
            angle_direction = direction
            for turn_index in range(1, config.turn_segments + 1):
                angle = angle_start + angle_direction * math.pi * (
                    turn_index / config.turn_segments
                )
                points.append(
                    (
                        end_east_m + turn_radius_m * math.cos(angle),
                        center_north_m + turn_radius_m * math.sin(angle),
                    )
                )

    route = CoverageRoute(reference, config, points)
    if not math.isclose(route.total_length_m, config.distance_m, abs_tol=1e-8):
        raise AssertionError(
            f"route length {route.total_length_m} does not match {config.distance_m}"
        )
    validate_route_inside_geotiff(route)
    return route


def validate_route_inside_geotiff(route: CoverageRoute) -> None:
    footprint_step = max(1, len(route.local_east_north_points) // 12)
    footprint_points = list(route.local_east_north_points[::footprint_step])
    if footprint_points[-1] != route.local_east_north_points[-1]:
        footprint_points.append(route.local_east_north_points[-1])
    for east_m, north_m in footprint_points:
        left_px, top_px, right_px, bottom_px = route.reference.local_footprint_pixel_bounds(
            east_m, north_m, route.config.footprint_width_m
        )
        if left_px < 0.0:
            raise ValueError("route camera footprint crosses the west GeoTIFF boundary")
        if right_px > route.reference.width_px:
            raise ValueError("route camera footprint crosses the east GeoTIFF boundary")
        if top_px < 0.0:
            raise ValueError("route camera footprint crosses the north GeoTIFF boundary")
        if bottom_px > route.reference.height_px:
            raise ValueError("route camera footprint crosses the south GeoTIFF boundary")


def write_planned_trajectory_csv(route: CoverageRoute, output_path: Path | str) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [field.name for field in RouteSample.__dataclass_fields__.values()]
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for sample in route.samples():
            writer.writerow(asdict(sample))


def ideal_groundtruth_rows(
    route: CoverageRoute,
    start_time: datetime,
) -> Iterable[dict[str, object]]:
    samples = list(route.samples())
    start_time_ns = datetime_to_unix_ns(start_time)
    velocities = [route.ideal_velocity_at(sample) for sample in samples]
    time_step_s = 1.0 / route.config.rate_hz
    accelerations: list[tuple[float, float, float]] = []
    for index, velocity in enumerate(velocities):
        if index == 0:
            other = velocities[min(1, len(velocities) - 1)]
            denominator_s = time_step_s
            first, second = velocity, other
        elif index == len(velocities) - 1:
            first, second = velocities[index - 1], velocity
            denominator_s = time_step_s
        else:
            first, second = velocities[index - 1], velocities[index + 1]
            denominator_s = 2.0 * time_step_s
        accelerations.append(
            tuple((second[axis] - first[axis]) / denominator_s for axis in range(3))
        )

    for sample, velocity, acceleration in zip(samples, velocities, accelerations):
        timestamp = start_time + timedelta(seconds=sample.scheduled_time_s)
        timestamp_ns = start_time_ns + int(
            round(sample.scheduled_time_s * 1_000_000_000)
        )
        yield {
            "sample_index": sample.frame_index,
            "schedule_frame_index": sample.frame_index,
            "scheduled_time_s": f"{sample.scheduled_time_s:.3f}",
            "actual_elapsed_s": f"{sample.scheduled_time_s:.3f}",
            "wall_time_utc": timestamp.isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            ),
            "state_timestamp_ns": timestamp_ns,
            "image_timestamp_ns": timestamp_ns,
            "source": "ideal_route",
            "position_north_m": f"{sample.local_north_m:.6f}",
            "position_east_m": f"{sample.local_east_m:.6f}",
            "position_down_m": f"{sample.local_down_m:.6f}",
            "velocity_north_mps": f"{velocity[0]:.6f}",
            "velocity_east_mps": f"{velocity[1]:.6f}",
            "velocity_down_mps": f"{velocity[2]:.6f}",
            "acceleration_north_mps2": f"{acceleration[0]:.6f}",
            "acceleration_east_mps2": f"{acceleration[1]:.6f}",
            "acceleration_down_mps2": f"{acceleration[2]:.6f}",
            "orientation_qx": "0.000000000",
            "orientation_qy": "0.000000000",
            "orientation_qz": "0.000000000",
            "orientation_qw": "1.000000000",
            "angular_velocity_x_radps": "0.000000000",
            "angular_velocity_y_radps": "0.000000000",
            "angular_velocity_z_radps": "0.000000000",
            "angular_acceleration_x_radps2": "0.000000000",
            "angular_acceleration_y_radps2": "0.000000000",
            "angular_acceleration_z_radps2": "0.000000000",
            "longitude_deg": f"{sample.longitude_deg:.10f}",
            "latitude_deg": f"{sample.latitude_deg:.10f}",
            "altitude_m": f"{route.config.altitude_m:.3f}",
        }


def write_ideal_groundtruth_csv(
    route: CoverageRoute,
    output_path: Path | str,
    start_time: datetime,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=TRAJECTORY_FIELDNAMES)
        writer.writeheader()
        writer.writerows(ideal_groundtruth_rows(route, start_time))


def write_mission_summary(route: CoverageRoute, output_path: Path | str, extra: dict | None = None) -> None:
    summary = route.to_summary()
    if extra:
        summary.update(extra)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def draw_route_preview(
    route: CoverageRoute,
    output_path: Path | str,
    max_size: tuple[int, int] = (1400, 1000),
) -> None:
    with Image.open(route.reference.path) as source:
        preview = source.convert("RGB")
    original_width, original_height = preview.size
    preview.thumbnail(max_size, Image.Resampling.LANCZOS)
    scale_x = preview.width / original_width
    scale_y = preview.height / original_height
    overlay = Image.new("RGBA", preview.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    def local_to_preview(east_m: float, north_m: float) -> tuple[float, float]:
        projected_x_m, projected_y_m = route.reference.local_to_projected(east_m, north_m)
        column_px, row_px = route.reference.projected_to_pixel(projected_x_m, projected_y_m)
        return column_px * scale_x, row_px * scale_y

    route_pixels = [local_to_preview(*point) for point in route.local_east_north_points]
    for east_m, north_m in route.local_east_north_points:
        left_px, top_px, right_px, bottom_px = route.reference.local_footprint_pixel_bounds(
            east_m, north_m, route.config.footprint_width_m
        )
        draw.rectangle(
            (
                left_px * scale_x,
                top_px * scale_y,
                right_px * scale_x,
                bottom_px * scale_y,
            ),
            outline=(0, 220, 255, 120),
            width=2,
        )
    draw.line(route_pixels, fill=(255, 40, 40, 255), width=max(3, preview.width // 350))
    marker_radius = max(5, preview.width // 180)
    start_x, start_y = route_pixels[0]
    end_x, end_y = route_pixels[-1]
    draw.ellipse(
        (start_x - marker_radius, start_y - marker_radius, start_x + marker_radius, start_y + marker_radius),
        fill=(30, 220, 80, 255),
        outline=(255, 255, 255, 255),
        width=2,
    )
    draw.ellipse(
        (end_x - marker_radius, end_y - marker_radius, end_x + marker_radius, end_y + marker_radius),
        fill=(255, 50, 40, 255),
        outline=(255, 255, 255, 255),
        width=2,
    )
    for time_s in range(10, int(route.config.moving_duration_s), 10):
        distance_m = min(time_s * route.config.speed_mps, route.total_length_m)
        east_m, north_m, _ = route.interpolate_local(distance_m)
        x_px, y_px = local_to_preview(east_m, north_m)
        radius = max(2, marker_radius // 3)
        draw.ellipse((x_px - radius, y_px - radius, x_px + radius, y_px + radius), fill=(255, 230, 0, 255))

    preview = Image.alpha_composite(preview.convert("RGBA"), overlay).convert("RGB")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    preview.save(output_path, quality=94, subsampling=0)


def default_tif_path() -> Path:
    return Path(__file__).resolve().with_name("input_map.tif")
