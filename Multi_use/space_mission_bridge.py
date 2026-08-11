#!/usr/bin/env python3
"""Space-mission bridge for LAESim SimpleSatellite.

This module intentionally avoids proprietary mission-analysis software. It can
use TLE/SGP4, CSV, or a mock orbit source, converts the real satellite state to
a scaled LAESim NED display pose, and computes simple target access geometry.
"""

import argparse
import csv
import datetime as _dt
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PYCLIENT = os.path.join(ROOT, "PythonClient")
if PYCLIENT not in sys.path:
    sys.path.insert(0, PYCLIENT)

RPCLIB_PORT_SATELLITE = 41491

WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)


@dataclass
class SpaceSample:
    timestamp: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    source: str = ""
    satellite_name: str = ""


@dataclass
class DisplayState:
    x: float
    y: float
    z: float
    yaw_rad: float
    north_m: float
    east_m: float
    down_m: float


@dataclass
class TargetSpec:
    name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float = 0.0
    kind: str = "fixed"


@dataclass
class AccessState:
    target_name: str
    target_kind: str
    source: str
    valid: bool
    access: bool
    azimuth_deg: float = float("nan")
    elevation_deg: float = float("nan")
    range_m: float = float("nan")
    off_nadir_deg: float = float("nan")
    sensor_off_axis_deg: float = float("nan")
    message: str = ""


@dataclass
class AttitudeSample:
    timestamp: str
    qx: float
    qy: float
    qz: float
    qw: float


def parse_time(value):
    if value is None or value == "":
        return None
    value = value.replace("T", " ").replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%d %b %Y %H:%M:%S.%f", "%d %b %Y %H:%M:%S"):
        try:
            parsed = _dt.datetime.strptime(value, fmt)
            return parsed.replace(tzinfo=_dt.timezone.utc) if parsed.tzinfo is None else parsed
        except ValueError:
            pass
    raise ValueError(f"Unsupported time format: {value}")


def format_time(value):
    if isinstance(value, _dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=_dt.timezone.utc)
        return value.astimezone(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def tle_epoch_from_line1(line1):
    """Return the UTC epoch encoded by a standard TLE line 1."""
    if len(line1) < 32 or not line1.startswith("1 "):
        raise ValueError("Invalid TLE line 1")
    short_year = int(line1[18:20])
    year = 2000 + short_year if short_year < 57 else 1900 + short_year
    day_of_year = float(line1[20:32])
    return (_dt.datetime(year, 1, 1, tzinfo=_dt.timezone.utc)
            + _dt.timedelta(days=day_of_year - 1.0))


def tle_age_days(provider, scenario_time=None):
    """Return absolute days between a provider's TLE epoch and scenario time."""
    epoch = getattr(provider, "epoch_utc", None)
    if epoch is None:
        return None
    scenario_time = scenario_time or _dt.datetime.now(_dt.timezone.utc)
    if scenario_time.tzinfo is None:
        scenario_time = scenario_time.replace(tzinfo=_dt.timezone.utc)
    return abs((scenario_time.astimezone(_dt.timezone.utc) - epoch).total_seconds()) / 86400.0


def parse_target(value):
    # NAME:LAT:LON[:ALT[:KIND]]
    parts = value.split(":", 4)
    if len(parts) < 3:
        raise ValueError("Target must be NAME:LAT:LON[:ALT[:KIND]]")
    return TargetSpec(
        name=parts[0],
        latitude_deg=float(parts[1]),
        longitude_deg=float(parts[2]),
        altitude_m=float(parts[3]) if len(parts) >= 4 and parts[3] else 0.0,
        kind=parts[4] if len(parts) >= 5 and parts[4] else "fixed")


def geodetic_to_ecef(lat_deg, lon_deg, alt_m):
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    x = (n + alt_m) * cos_lat * math.cos(lon)
    y = (n + alt_m) * cos_lat * math.sin(lon)
    z = (n * (1.0 - WGS84_E2) + alt_m) * sin_lat
    return x, y, z


def ecef_to_geodetic(x, y, z):
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1.0 - WGS84_E2))
    for _ in range(8):
        sin_lat = math.sin(lat)
        n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
        alt = p / max(1e-12, math.cos(lat)) - n
        lat = math.atan2(z, p * (1.0 - WGS84_E2 * n / (n + alt)))
    sin_lat = math.sin(lat)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    alt = p / max(1e-12, math.cos(lat)) - n
    return math.degrees(lat), normalize_lon_deg(math.degrees(lon)), alt


def ecef_to_ned(lat_ref_deg, lon_ref_deg, alt_ref_m, lat_deg, lon_deg, alt_m):
    ref = geodetic_to_ecef(lat_ref_deg, lon_ref_deg, alt_ref_m)
    cur = geodetic_to_ecef(lat_deg, lon_deg, alt_m)
    dx, dy, dz = cur[0] - ref[0], cur[1] - ref[1], cur[2] - ref[2]
    lat = math.radians(lat_ref_deg)
    lon = math.radians(lon_ref_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)
    north = -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz
    east = -sin_lon * dx + cos_lon * dy
    down = -cos_lat * cos_lon * dx - cos_lat * sin_lon * dy - sin_lat * dz
    return north, east, down


def normalize_lon_deg(lon):
    while lon > 180.0:
        lon -= 360.0
    while lon < -180.0:
        lon += 360.0
    return lon


def julian_date(dt):
    if dt.tzinfo is not None:
        dt = dt.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    year = dt.year
    month = dt.month
    day = dt.day
    hour = dt.hour + dt.minute / 60.0 + (dt.second + dt.microsecond * 1e-6) / 3600.0
    if month <= 2:
        year -= 1
        month += 12
    a = math.floor(year / 100)
    b = 2 - a + math.floor(a / 4)
    jd0 = math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + b - 1524.5
    return jd0 + hour / 24.0


def gmst_rad(dt):
    jd = julian_date(dt)
    t = (jd - 2451545.0) / 36525.0
    gmst_deg = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * t * t - (t * t * t) / 38710000.0
    return math.radians(gmst_deg % 360.0)


def teme_km_to_ecef_m(position_km, dt):
    # MVP approximation: rotate TEME by GMST. This is sufficient for visual and
    # mission-geometry demonstrations, but not for precision astrometry.
    theta = gmst_rad(dt)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    x = position_km[0] * 1000.0
    y = position_km[1] * 1000.0
    z = position_km[2] * 1000.0
    return cos_t * x + sin_t * y, -sin_t * x + cos_t * y, z


def compute_course_yaw(previous, current, fallback_yaw_rad):
    if previous is None:
        return fallback_yaw_rad
    dn = current.north_m - previous.north_m
    de = current.east_m - previous.east_m
    if abs(dn) + abs(de) < 1e-6:
        return fallback_yaw_rad
    return math.atan2(de, dn)


class CsvProvider:
    def __init__(self, path, loop=True):
        self.rows = []
        with open(path, "r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                self.rows.append(self._parse_row(row))
        if not self.rows:
            raise RuntimeError(f"No rows found in CSV: {path}")
        self.loop = loop
        self.index = 0

    @staticmethod
    def _pick(row, names):
        lowered = {k.lower(): v for k, v in row.items()}
        for name in names:
            if name.lower() in lowered and lowered[name.lower()] not in (None, ""):
                return lowered[name.lower()]
        raise KeyError(f"Missing any of CSV columns: {', '.join(names)}")

    def _parse_row(self, row):
        timestamp = row.get("time") or row.get("timestamp") or row.get("scenario_time") or ""
        lat = float(self._pick(row, ("lat", "latitude", "latitude_deg")))
        lon = float(self._pick(row, ("lon", "longitude", "longitude_deg")))
        if any(k.lower() in {name.lower() for name in row.keys()} for k in ("alt_m", "altitude_m")):
            alt = float(self._pick(row, ("alt_m", "altitude_m")))
        else:
            alt = float(self._pick(row, ("alt", "altitude", "alt_km", "altitude_km")))
            if abs(alt) < 10000.0:
                alt *= 1000.0
        name = row.get("satellite") or row.get("satellite_name") or ""
        return SpaceSample(timestamp, lat, lon, alt, "csv", name)

    def sample(self, _scenario_time):
        row = self.rows[self.index]
        self.index += 1
        if self.index >= len(self.rows):
            self.index = 0 if self.loop else len(self.rows) - 1
        return row


class MockProvider:
    def __init__(self, reference_lat, reference_lon, altitude_m, radius_m, period_s):
        self.reference_lat = reference_lat
        self.reference_lon = reference_lon
        self.altitude_m = altitude_m
        self.radius_m = radius_m
        self.period_s = period_s
        self.start = time.monotonic()

    def sample(self, scenario_time):
        elapsed = max(0.0, time.monotonic() - self.start)
        angle = 2.0 * math.pi * (elapsed % self.period_s) / self.period_s
        north = self.radius_m * math.cos(angle)
        east = self.radius_m * math.sin(angle)
        dlat = north / 111320.0
        dlon = east / (111320.0 * max(0.1, math.cos(math.radians(self.reference_lat))))
        stamp = format_time(scenario_time) if scenario_time else format_time(_dt.datetime.now(_dt.timezone.utc))
        return SpaceSample(stamp, self.reference_lat + dlat, self.reference_lon + dlon, self.altitude_m, "mock", "MockSatellite")


class TleProvider:
    def __init__(self, path, satellite_name="", satellite_index=0):
        try:
            from sgp4.api import Satrec
        except ImportError as exc:
            raise RuntimeError("TLE provider requires the sgp4 package: pip install sgp4") from exc

        entries = self._load_tles(path)
        if not entries:
            raise RuntimeError(f"No TLE entries found in: {path}")

        selected = None
        if satellite_name:
            for entry in entries:
                if entry[0].lower() == satellite_name.lower():
                    selected = entry
                    break
            if selected is None:
                raise RuntimeError(f"Satellite name not found in TLE file: {satellite_name}")
        else:
            if satellite_index < 0 or satellite_index >= len(entries):
                raise RuntimeError(f"Satellite index out of range: {satellite_index}")
            selected = entries[satellite_index]

        self.name, self.line1, self.line2 = selected
        self.epoch_utc = tle_epoch_from_line1(self.line1)
        self.satrec = Satrec.twoline2rv(self.line1, self.line2)

    @staticmethod
    def _load_tles(path):
        with open(path, "r", encoding="utf-8-sig") as handle:
            lines = [line.strip() for line in handle.readlines() if line.strip()]
        entries = []
        i = 0
        while i < len(lines):
            if lines[i].startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
                entries.append((f"SAT-{len(entries) + 1}", lines[i], lines[i + 1]))
                i += 2
            elif i + 2 < len(lines) and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
                entries.append((lines[i], lines[i + 1], lines[i + 2]))
                i += 3
            else:
                i += 1
        return entries

    def sample(self, scenario_time):
        if scenario_time is None:
            scenario_time = _dt.datetime.now(_dt.timezone.utc)
        if scenario_time.tzinfo is None:
            scenario_time = scenario_time.replace(tzinfo=_dt.timezone.utc)
        utc = scenario_time.astimezone(_dt.timezone.utc)
        jd = julian_date(utc)
        whole = math.floor(jd)
        fraction = jd - whole
        error, position_km, _velocity_km_s = self.satrec.sgp4(whole, fraction)
        if error != 0:
            raise RuntimeError(f"SGP4 propagation failed with error code {error}")
        ecef = teme_km_to_ecef_m(position_km, utc)
        lat, lon, alt = ecef_to_geodetic(*ecef)
        return SpaceSample(format_time(utc), lat, lon, alt, "tle-sgp4", self.name)


class OrekitTleProvider:
    def __init__(self, path, satellite_name="", satellite_index=0, orekit_data_path=""):
        try:
            import orekit
            from orekit.pyhelpers import setup_orekit_curdir
        except ImportError as exc:
            raise RuntimeError("Orekit provider requires the Orekit Python wrapper and a configured orekit-data directory.") from exc

        self.orekit = orekit
        self.vm = orekit.initVM()
        if orekit_data_path:
            data_file = orekit_data_path
            if os.path.isdir(data_file):
                data_file = os.path.join(data_file, "orekit-data.zip")
            if not os.path.isfile(data_file):
                raise RuntimeError(f"Orekit data archive not found: {data_file}")
            setup_orekit_curdir(data_file)
        else:
            setup_orekit_curdir()

        from org.orekit.propagation.analytical.tle import TLE, TLEPropagator
        from org.orekit.time import AbsoluteDate, TimeScalesFactory
        from org.orekit.frames import FramesFactory
        from org.orekit.bodies import OneAxisEllipsoid
        from org.orekit.utils import Constants, IERSConventions

        entries = TleProvider._load_tles(path)
        if not entries:
            raise RuntimeError(f"No TLE entries found in: {path}")
        selected = None
        if satellite_name:
            for entry in entries:
                if entry[0].lower() == satellite_name.lower():
                    selected = entry
                    break
            if selected is None:
                raise RuntimeError(f"Satellite name not found in TLE file: {satellite_name}")
        else:
            if satellite_index < 0 or satellite_index >= len(entries):
                raise RuntimeError(f"Satellite index out of range: {satellite_index}")
            selected = entries[satellite_index]

        self.name, self.line1, self.line2 = selected
        self.epoch_utc = tle_epoch_from_line1(self.line1)
        self.TLE = TLE
        self.TLEPropagator = TLEPropagator
        self.AbsoluteDate = AbsoluteDate
        self.TimeScalesFactory = TimeScalesFactory
        self.itrf = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
        self.earth = OneAxisEllipsoid(
            Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
            Constants.WGS84_EARTH_FLATTENING,
            self.itrf)
        self.propagator = self._new_propagator()

    def _new_propagator(self):
        return self.TLEPropagator.selectExtrapolator(self.TLE(self.line1, self.line2))

    def _absolute_date(self, dt):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        dt = dt.astimezone(_dt.timezone.utc)
        seconds = dt.second + dt.microsecond * 1e-6
        return self.AbsoluteDate(
            dt.year, dt.month, dt.day, dt.hour, dt.minute, seconds,
            self.TimeScalesFactory.getUTC())

    def sample(self, scenario_time):
        if scenario_time is None:
            scenario_time = _dt.datetime.now(_dt.timezone.utc)
        utc = scenario_time.astimezone(_dt.timezone.utc) if scenario_time.tzinfo else scenario_time.replace(tzinfo=_dt.timezone.utc)
        date = self._absolute_date(utc)
        pv = self.propagator.propagate(date).getPVCoordinates(self.itrf)
        point = self.earth.transform(pv.getPosition(), self.itrf, date)
        return SpaceSample(
            format_time(utc),
            math.degrees(point.getLatitude()),
            math.degrees(point.getLongitude()),
            point.getAltitude(),
            "orekit-tle",
            self.name)

    def access_windows(
        self,
        start_time,
        stop_time,
        target,
        min_elevation_deg,
        max_check_s=60.0,
        threshold_s=0.1,
    ):
        """Locate ground-target elevation crossings with Orekit event detection."""
        from orekit.pyhelpers import absolutedate_to_datetime
        from org.orekit.bodies import GeodeticPoint
        from org.orekit.frames import TopocentricFrame
        from org.orekit.propagation.events import ElevationDetector, EventsLogger
        from org.orekit.propagation.events.handlers import ContinueOnEvent

        if stop_time <= start_time:
            return []
        topocentric = TopocentricFrame(
            self.earth,
            GeodeticPoint(
                math.radians(target.latitude_deg),
                math.radians(target.longitude_deg),
                target.altitude_m,
            ),
            target.name,
        )
        raw_detector = ElevationDetector(
            float(max_check_s), float(threshold_s), topocentric
        ).withConstantElevation(math.radians(min_elevation_deg))
        logger = EventsLogger()
        propagator = self._new_propagator()
        start_date = self._absolute_date(start_time)
        stop_date = self._absolute_date(stop_time)
        initial_access = raw_detector.g(propagator.propagate(start_date)) >= 0.0
        detector = raw_detector.withHandler(ContinueOnEvent())
        propagator.addEventDetector(logger.monitorDetector(detector))
        propagator.propagate(start_date, stop_date)

        intervals = []
        active_start = start_time if initial_access else None
        for event in logger.getLoggedEvents():
            event_time = absolutedate_to_datetime(event.getDate(), tz_aware=True)
            event_time = event_time.astimezone(_dt.timezone.utc)
            if event.isIncreasing():
                active_start = event_time
            elif active_start is not None:
                intervals.append((active_start, event_time))
                active_start = None
        if active_start is not None:
            intervals.append((active_start, stop_time))
        return intervals


def create_provider(args):
    if args.provider == "csv":
        return CsvProvider(args.csv, loop=not args.no_csv_loop)
    if args.provider == "mock":
        return MockProvider(args.reference_lat, args.reference_lon, args.mock_altitude_m, args.mock_radius_m, args.mock_period_s)
    if args.provider == "tle":
        return TleProvider(args.tle, args.satellite_name, args.satellite_index)
    if args.provider == "orekit-tle":
        return OrekitTleProvider(args.tle, args.satellite_name, args.satellite_index, getattr(args, "orekit_data", ""))
    raise ValueError(args.provider)


def build_display_state(sample, args, previous_display):
    north, east, down = ecef_to_ned(
        args.reference_lat,
        args.reference_lon,
        args.reference_alt,
        sample.latitude_deg,
        sample.longitude_deg,
        sample.altitude_m)

    real_state = DisplayState(0.0, 0.0, 0.0, 0.0, north, east, down)
    if args.display_mode == "fixed-overhead":
        x = args.fixed_x
        y = args.fixed_y
        z = -abs(args.fixed_display_altitude)
    elif args.display_mode == "global-track":
        lat = math.radians(sample.latitude_deg)
        reference_lat = math.radians(args.reference_lat)
        delta_lon = math.radians(normalize_lon_deg(sample.longitude_deg - args.reference_lon))
        radius = abs(args.global_track_radius)
        x = radius * (
            math.cos(reference_lat) * math.sin(lat)
            - math.sin(reference_lat) * math.cos(lat) * math.cos(delta_lon)
        )
        y = radius * math.cos(lat) * math.sin(delta_lon)
        z = -abs(args.fixed_display_altitude)
    elif args.display_mode == "subpoint-only":
        x = north * args.horizontal_scale
        y = east * args.horizontal_scale
        z = -abs(args.fixed_display_altitude)
    else:
        display_alt = max(args.min_display_altitude, (sample.altitude_m - args.reference_alt) * args.vertical_scale)
        x = north * args.horizontal_scale
        y = east * args.horizontal_scale
        z = -display_alt

    fallback_yaw = math.radians(args.fixed_yaw_deg)
    yaw = fallback_yaw if args.yaw_mode == "fixed" else compute_course_yaw(previous_display, real_state, fallback_yaw)
    return DisplayState(x, y, z, yaw, north, east, down)


def compute_access(sample, target, args):
    sat_n, sat_e, sat_d = ecef_to_ned(args.reference_lat, args.reference_lon, args.reference_alt, sample.latitude_deg, sample.longitude_deg, sample.altitude_m)
    tgt_n, tgt_e, tgt_d = ecef_to_ned(args.reference_lat, args.reference_lon, args.reference_alt, target.latitude_deg, target.longitude_deg, target.altitude_m)
    dn = sat_n - tgt_n
    de = sat_e - tgt_e
    dd = sat_d - tgt_d
    rng = math.sqrt(dn * dn + de * de + dd * dd)
    if rng <= 1e-6:
        return AccessState(target.name, target.kind, "local-geometry", False, False, message="Satellite and target are colocated")
    elevation = math.degrees(math.asin(-dd / rng))
    azimuth = math.degrees(math.atan2(de, dn))
    if azimuth < 0.0:
        azimuth += 360.0
    sat_ecef = geodetic_to_ecef(
        sample.latitude_deg, sample.longitude_deg, sample.altitude_m
    )
    target_ecef = geodetic_to_ecef(
        target.latitude_deg, target.longitude_deg, target.altitude_m
    )
    nadir = tuple(-value for value in sat_ecef)
    line_of_sight = tuple(right - left for left, right in zip(sat_ecef, target_ecef))
    nadir_norm = math.sqrt(sum(value * value for value in nadir))
    los_norm = math.sqrt(sum(value * value for value in line_of_sight))
    cosine = sum(left * right for left, right in zip(nadir, line_of_sight)) / (
        nadir_norm * los_norm
    )
    off_nadir_deg = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))

    pointing_mode = str(getattr(args, "sensor_pointing_mode", "none")).lower()
    side_look_angle_deg = float(getattr(args, "side_look_angle_deg", 0.0))
    if pointing_mode == "target-track":
        sensor_off_axis_deg = 0.0
    elif pointing_mode == "side-look":
        sensor_off_axis_deg = abs(off_nadir_deg - side_look_angle_deg)
    else:
        sensor_off_axis_deg = off_nadir_deg

    access = elevation >= args.min_elevation_deg
    message = "" if access else "below_min_elevation"
    max_range_m = getattr(args, "max_range_m", None)
    if access and max_range_m is not None and float(max_range_m) > 0.0 and rng > float(max_range_m):
        access = False
        message = "range_exceeded"
    max_off_nadir_deg = getattr(args, "max_off_nadir_deg", None)
    if (
        access
        and max_off_nadir_deg is not None
        and float(max_off_nadir_deg) < 180.0
        and off_nadir_deg > float(max_off_nadir_deg)
    ):
        access = False
        message = "off_nadir_exceeded"
    sensor_half_angle_deg = getattr(args, "sensor_half_angle_deg", None)
    if (
        access
        and pointing_mode != "none"
        and sensor_half_angle_deg is not None
        and sensor_off_axis_deg > float(sensor_half_angle_deg)
    ):
        access = False
        message = "outside_sensor_fov"
    return AccessState(
        target_name=target.name,
        target_kind=target.kind,
        source="local-geometry",
        valid=True,
        access=access,
        azimuth_deg=azimuth,
        elevation_deg=elevation,
        range_m=rng,
        off_nadir_deg=off_nadir_deg,
        sensor_off_axis_deg=sensor_off_axis_deg,
        message=message)


def _refine_access_transition(provider, target, args, left, right, tolerance_s):
    left_access = compute_access(provider.sample(left), target, args).access
    while (right - left).total_seconds() > tolerance_s:
        midpoint = left + (right - left) / 2
        midpoint_access = compute_access(provider.sample(midpoint), target, args).access
        if midpoint_access == left_access:
            left = midpoint
        else:
            right = midpoint
    return right


def find_next_access_window(
    provider,
    target,
    args,
    start_time,
    search_hours=48.0,
    step_s=30.0,
    tolerance_s=0.25,
):
    """Find the current or next sampled access window for a time-aware provider."""
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=_dt.timezone.utc)
    stop_time = start_time + _dt.timedelta(hours=max(0.0, search_hours))
    step = _dt.timedelta(seconds=max(0.1, step_s))
    current_time = start_time
    current_access = compute_access(provider.sample(current_time), target, args).access
    rise_time = current_time if current_access else None

    while current_time < stop_time:
        next_time = min(stop_time, current_time + step)
        next_access = compute_access(provider.sample(next_time), target, args).access
        if not current_access and next_access:
            rise_time = _refine_access_transition(
                provider, target, args, current_time, next_time, tolerance_s
            )
        elif current_access and not next_access and rise_time is not None:
            set_time = _refine_access_transition(
                provider, target, args, current_time, next_time, tolerance_s
            )
            return rise_time, set_time
        current_time = next_time
        current_access = next_access

    if rise_time is not None:
        return rise_time, stop_time
    return None


def write_jsonl(path, record):
    if not path:
        return
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, allow_nan=True) + "\n")


def import_airsim():
    import airsim
    return airsim


def yaw_to_quaternion_values(yaw_rad):
    half = yaw_rad * 0.5
    return 0.0, 0.0, math.sin(half), math.cos(half)


def euler_to_quaternion_values(roll_rad, pitch_rad, yaw_rad):
    cr = math.cos(roll_rad * 0.5)
    sr = math.sin(roll_rad * 0.5)
    cp = math.cos(pitch_rad * 0.5)
    sp = math.sin(pitch_rad * 0.5)
    cy = math.cos(yaw_rad * 0.5)
    sy = math.sin(yaw_rad * 0.5)
    qw = cr * cp * cy + sr * sp * sy
    qx = sr * cp * cy - cr * sp * sy
    qy = cr * sp * cy + sr * cp * sy
    qz = cr * cp * sy - sr * sp * cy
    return qx, qy, qz, qw


class AttitudeCsvProvider:
    def __init__(self, path, loop=True):
        self.rows = []
        with open(path, "r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                self.rows.append(self._parse_row(row))
        if not self.rows:
            raise RuntimeError(f"No rows found in attitude CSV: {path}")
        self.loop = loop
        self.index = 0

    @staticmethod
    def _get(row, names, default=None):
        lowered = {k.lower(): v for k, v in row.items()}
        for name in names:
            if name.lower() in lowered and lowered[name.lower()] not in (None, ""):
                return lowered[name.lower()]
        return default

    def _parse_row(self, row):
        timestamp = row.get("time") or row.get("timestamp") or row.get("scenario_time") or ""
        qw = self._get(row, ("qw", "q0", "sigma_bn_0"))
        qx = self._get(row, ("qx", "q1", "sigma_bn_1"))
        qy = self._get(row, ("qy", "q2", "sigma_bn_2"))
        qz = self._get(row, ("qz", "q3", "sigma_bn_3"))
        if all(value is not None for value in (qx, qy, qz, qw)):
            qx, qy, qz, qw = float(qx), float(qy), float(qz), float(qw)
        else:
            roll = math.radians(float(self._get(row, ("roll_deg", "roll"), 0.0)))
            pitch = math.radians(float(self._get(row, ("pitch_deg", "pitch"), 0.0)))
            yaw = math.radians(float(self._get(row, ("yaw_deg", "yaw"), 0.0)))
            qx, qy, qz, qw = euler_to_quaternion_values(roll, pitch, yaw)
        norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
        if norm <= 1e-9:
            raise RuntimeError("Attitude quaternion has zero norm")
        return AttitudeSample(timestamp, qx / norm, qy / norm, qz / norm, qw / norm)

    def sample(self):
        row = self.rows[self.index]
        self.index += 1
        if self.index >= len(self.rows):
            self.index = 0 if self.loop else len(self.rows) - 1
        return row


def set_laesim_pose(client, vehicle_name, display, airsim_module=None, attitude=None):
    airsim_module = airsim_module or import_airsim()
    if attitude is None:
        orientation = airsim_module.to_quaternion(0.0, 0.0, display.yaw_rad)
    else:
        orientation = airsim_module.Quaternionr(attitude.qx, attitude.qy, attitude.qz, attitude.qw)
    pose = airsim_module.Pose(
        airsim_module.Vector3r(display.x, display.y, display.z),
        orientation)
    client.simSetVehiclePose(pose, True, vehicle_name)


def parse_args():
    parser = argparse.ArgumentParser(description="Synchronize a satellite mission model to a LAESim SimpleSatellite visual model.")
    parser.add_argument("--provider", choices=("tle", "orekit-tle", "csv", "mock"), default="tle")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=RPCLIB_PORT_SATELLITE)
    parser.add_argument("--vehicle", default="Satellite")
    parser.add_argument("--rate", type=float, default=2.0)
    parser.add_argument("--clock-speed", type=float, default=1.0)
    parser.add_argument("--start-time", default="")
    parser.add_argument("--duration", type=float, default=0.0, help="Stop after this many wall-clock seconds. 0 means run forever.")
    parser.add_argument("--no-airsim", action="store_true", help="Only print converted states; do not connect to LAESim.")
    parser.add_argument("--print-every", type=int, default=10)
    parser.add_argument("--target", action="append", default=[], help="Mission target as NAME:LAT:LON[:ALT[:KIND]]. Can be repeated.")
    parser.add_argument("--min-elevation-deg", type=float, default=5.0)
    parser.add_argument("--max-range-m", type=float, default=0.0)
    parser.add_argument("--max-off-nadir-deg", type=float, default=180.0)
    parser.add_argument(
        "--sensor-pointing-mode",
        choices=("none", "nadir", "side-look", "target-track"),
        default="none",
    )
    parser.add_argument("--sensor-half-angle-deg", type=float, default=180.0)
    parser.add_argument("--side-look-angle-deg", type=float, default=0.0)
    parser.add_argument("--mission-report-jsonl", default="", help="Optional JSONL output with ephemeris and access states.")
    parser.add_argument("--attitude-csv", default="", help="Optional Basilisk or custom attitude CSV with quaternion or Euler columns.")
    parser.add_argument("--no-attitude-loop", action="store_true")

    parser.add_argument("--reference-lat", type=float, default=22.591164)
    parser.add_argument("--reference-lon", type=float, default=113.975317)
    parser.add_argument("--reference-alt", type=float, default=0.0)
    parser.add_argument(
        "--display-mode",
        choices=("scaled-ned", "fixed-overhead", "subpoint-only", "global-track"),
        default="scaled-ned",
    )
    parser.add_argument("--horizontal-scale", type=float, default=0.001)
    parser.add_argument("--vertical-scale", type=float, default=0.001)
    parser.add_argument("--min-display-altitude", type=float, default=80.0)
    parser.add_argument("--fixed-display-altitude", type=float, default=300.0)
    parser.add_argument("--fixed-x", type=float, default=0.0)
    parser.add_argument("--fixed-y", type=float, default=0.0)
    parser.add_argument("--global-track-radius", type=float, default=80.0)
    parser.add_argument("--yaw-mode", choices=("course", "fixed"), default="course")
    parser.add_argument("--fixed-yaw-deg", type=float, default=0.0)

    parser.add_argument("--tle", default=os.path.join(ROOT, "Multi_use", "space_mission_sample.tle"))
    parser.add_argument("--orekit-data", default="", help="Optional orekit-data directory for --provider orekit-tle.")
    parser.add_argument("--satellite-name", default="")
    parser.add_argument("--satellite-index", type=int, default=0)
    parser.add_argument("--max-tle-age-days", type=float, default=14.0)
    parser.add_argument("--require-fresh-tle", action="store_true")
    parser.add_argument("--csv", default="")
    parser.add_argument("--no-csv-loop", action="store_true")
    parser.add_argument("--mock-altitude-m", type=float, default=500000.0)
    parser.add_argument("--mock-radius-m", type=float, default=10000.0)
    parser.add_argument("--mock-period-s", type=float, default=120.0)
    return parser.parse_args()


def main():
    args = parse_args()
    if args.provider == "csv" and not args.csv:
        raise SystemExit("--provider csv requires --csv path")

    provider = create_provider(args)
    targets = [parse_target(value) for value in args.target]
    attitude_provider = AttitudeCsvProvider(args.attitude_csv, loop=not args.no_attitude_loop) if args.attitude_csv else None
    scenario_start = parse_time(args.start_time) if args.start_time else None
    age_days = tle_age_days(provider, scenario_start)
    if age_days is not None and age_days > args.max_tle_age_days:
        message = (
            f"TLE epoch {format_time(provider.epoch_utc)} is {age_days:.1f} days "
            f"from the scenario time; configured limit is {args.max_tle_age_days:.1f} days"
        )
        if args.require_fresh_tle:
            raise SystemExit(message)
        print(f"WARNING: {message}")
    wall_start = time.monotonic()

    client = None
    airsim_module = None
    if not args.no_airsim:
        airsim_module = import_airsim()
        client = airsim_module.SatelliteClient(ip=args.host, port=args.port)
        client.confirmConnection()
        client.enableApiControl(True, args.vehicle)
        client.armDisarm(True, args.vehicle)
        client.setSatelliteControls(airsim_module.SatelliteControls(), vehicle_name=args.vehicle)

    previous_real = None
    tick = 0
    period = 1.0 / max(0.001, args.rate)
    while True:
        elapsed = time.monotonic() - wall_start
        if args.duration > 0.0 and elapsed >= args.duration:
            break
        scenario_time = scenario_start + _dt.timedelta(seconds=elapsed * args.clock_speed) if scenario_start else None
        sample = provider.sample(scenario_time)
        display = build_display_state(sample, args, previous_real)
        attitude = attitude_provider.sample() if attitude_provider else None
        previous_real = DisplayState(0.0, 0.0, 0.0, display.yaw_rad, display.north_m, display.east_m, display.down_m)
        access_states = [compute_access(sample, target, args) for target in targets]

        if client is not None:
            set_laesim_pose(client, args.vehicle, display, airsim_module, attitude)

        if tick % max(1, args.print_every) == 0:
            sat_label = sample.satellite_name or args.vehicle
            print(
                f"[{tick}] {sample.timestamp} sat={sat_label} src={sample.source} "
                f"lat={sample.latitude_deg:.6f} lon={sample.longitude_deg:.6f} alt_m={sample.altitude_m:.1f} "
                f"ned=({display.north_m:.1f},{display.east_m:.1f},{display.down_m:.1f}) "
                f"laesim=({display.x:.2f},{display.y:.2f},{display.z:.2f}) yaw_deg={math.degrees(display.yaw_rad):.1f}")
            if attitude is not None:
                print(f"    attitude q=({attitude.qx:.4f},{attitude.qy:.4f},{attitude.qz:.4f},{attitude.qw:.4f}) src=csv")
            for access in access_states:
                print(
                    f"    target={access.target_name} kind={access.target_kind} access={access.access} "
                    f"elev={access.elevation_deg:.2f} az={access.azimuth_deg:.2f} "
                    f"range_m={access.range_m:.1f} valid={access.valid} {access.message}")

        write_jsonl(args.mission_report_jsonl, {
            "timestamp": sample.timestamp,
            "vehicle": args.vehicle,
            "sample": asdict(sample),
            "display": asdict(display),
            "access": [asdict(state) for state in access_states],
        })

        tick += 1
        time.sleep(period)


if __name__ == "__main__":
    main()
