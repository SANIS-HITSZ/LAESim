import csv
import json
import os
import tempfile
import unittest

from NetworkSim.python.export_space_demo_report import export_report


class ExportSpaceDemoReportTest(unittest.TestCase):
    def test_export_report(self):
        summary = {
            "metadata": {
                "provider": "tle",
                "vehicles": ["Satellite", "Satellite2"],
                "targets": ["Car"],
            },
            "scenario_start": "2026-07-23T00:00:00Z",
            "scenario_stop": "2026-07-23T00:10:00Z",
            "sample_count": 2,
            "selection_statistics": {
                "Car": {
                    "selected_satellite": "Satellite2",
                    "handover_count": 1,
                    "acquisition_count": 2,
                    "outage_count": 1,
                    "completed_outage_count": 1,
                    "total_outage_s_including_current": 12.5,
                    "max_outage_s_including_current": 12.5,
                    "mean_revisit_s": 12.5,
                }
            },
            "selection_events": [{
                "scenario_time": "2026-07-23T00:05:00Z",
                "target": "Car",
                "previous_satellite": "Satellite",
                "selected_satellite": "Satellite2",
                "outage": False,
                "interruption_s": 0.0,
            }],
        }
        records = [
            {"isl_links": [{"source": "Satellite", "destination": "Satellite2", "access": True, "range_m": 1000000.0}]},
            {"isl_links": [{"source": "Satellite", "destination": "Satellite2", "access": False, "range_m": 1200000.0}]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            paths = export_report(summary, records, directory)
            self.assertEqual(len(paths), 4)
            for path in paths:
                self.assertTrue(os.path.isfile(path))
            with open(paths[0], "r", encoding="utf-8") as handle:
                markdown = handle.read()
            self.assertIn("Satellite2", markdown)
            self.assertIn("50.00%", markdown)
            with open(paths[3], "r", encoding="utf-8-sig", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["samples"], "2")
            self.assertEqual(row["availability_fraction"], "0.5")


if __name__ == "__main__":
    unittest.main()
