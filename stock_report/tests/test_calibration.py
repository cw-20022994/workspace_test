"""Calibration helper tests."""

import unittest

from stock_report.analysis.calibration import build_scoring_calibration_report
from stock_report.analysis.scoring_profile import default_scoring_profile


class CalibrationTests(unittest.TestCase):
    def test_calibration_report_keeps_profile_when_evidence_is_insufficient(self) -> None:
        aggregate = {
            "counts": {
                "snapshots_included": 1,
                "status_by_horizon": {
                    "20d": {
                        "pending": 4,
                    }
                },
            },
            "verdict_summary_by_horizon": {
                "20d": {
                    "review": {"completed": 0, "avg_excess_return": None},
                    "hold": {"completed": 0, "avg_excess_return": None},
                }
            },
            "score_band_summary_by_horizon": {
                "20d": {
                    "50-59": {"completed": 0, "avg_excess_return": None},
                    "70-79": {"completed": 0, "avg_excess_return": None},
                }
            },
        }

        report = build_scoring_calibration_report(
            aggregate_summary=aggregate,
            current_profile=default_scoring_profile(),
            generated_at_utc="2026-03-19T00:00:00+00:00",
        )

        self.assertFalse(report["auto_applied"])
        self.assertEqual(report["changes"], [])
        self.assertIn("완료 관측치", report["reasons"][0])

    def test_calibration_report_can_raise_threshold_and_shift_weights(self) -> None:
        aggregate = {
            "counts": {
                "snapshots_included": 4,
                "status_by_horizon": {
                    "20d": {
                        "complete": 16,
                    }
                },
            },
            "verdict_summary_by_horizon": {
                "20d": {
                    "review": {"completed": 8, "avg_excess_return": -1.0},
                    "hold": {"completed": 8, "avg_excess_return": 2.0},
                }
            },
            "score_band_summary_by_horizon": {
                "20d": {
                    "50-59": {"completed": 6, "avg_excess_return": 3.0},
                    "70-79": {"completed": 6, "avg_excess_return": 0.0},
                }
            },
        }

        report = build_scoring_calibration_report(
            aggregate_summary=aggregate,
            current_profile=default_scoring_profile(),
            generated_at_utc="2026-03-19T00:00:00+00:00",
        )

        self.assertGreater(len(report["changes"]), 0)
        fields = {item["field"] for item in report["changes"]}
        self.assertIn("verdict_thresholds.review_min", fields)
        self.assertIn("weights.news", fields)
        self.assertIn("weights.risk", fields)


if __name__ == "__main__":
    unittest.main()
