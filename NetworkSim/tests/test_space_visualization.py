import json
import math
import os
import tempfile
import unittest

from NetworkSim.python.space_visualization import (
    VehicleOrigin,
    circle_points,
    coverage_central_angle_rad,
    load_vehicle_origins,
    projected_coverage_radius,
    to_global_ned,
)


class SpaceVisualizationTest(unittest.TestCase):
    def test_load_origins_and_global_position(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"Vehicles": {"Satellite": {"X": 10, "Y": -3, "Z": -80}}}, handle)
            origins = load_vehicle_origins(path)
        self.assertEqual(origins["Satellite"], VehicleOrigin(10.0, -3.0, -80.0))
        self.assertEqual(to_global_ned((1, 2, -5), origins["Satellite"]), (11.0, -1.0, -85.0))

    def test_coverage_angle_is_physical_and_monotonic(self):
        low = coverage_central_angle_rad(400000.0, 5.0)
        high = coverage_central_angle_rad(800000.0, 5.0)
        strict = coverage_central_angle_rad(800000.0, 30.0)
        self.assertGreater(low, 0.0)
        self.assertGreater(high, low)
        self.assertLess(strict, high)

    def test_projected_radius_stays_within_display_globe(self):
        radius = projected_coverage_radius(80.0, 500000.0, 5.0)
        self.assertGreater(radius, 0.0)
        self.assertLess(radius, 80.0)

    def test_circle_is_closed(self):
        points = circle_points(2.0, -3.0, 0.0, 10.0, segments=12)
        self.assertEqual(len(points), 13)
        for left, right in zip(points[0], points[-1]):
            self.assertTrue(math.isclose(left, right, abs_tol=1e-9))

    def test_circle_rejects_too_few_segments(self):
        with self.assertRaises(ValueError):
            circle_points(0.0, 0.0, 0.0, 1.0, segments=4)


if __name__ == "__main__":
    unittest.main()
