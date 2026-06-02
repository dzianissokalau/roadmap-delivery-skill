import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class EvidenceBenchmarkTests(unittest.TestCase):
    maxDiff = None

    def run_cli(self, *args):
        proc = subprocess.run(
            [sys.executable, "-m", "roadmap_delivery.cli", *args],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        return json.loads(proc.stdout)

    def scenario_by_id(self, report):
        return {scenario["id"]: scenario for scenario in report["scenarios"]}

    def issue_codes(self, scenario):
        return {issue["code"] for issue in scenario["detected_issues"]}

    def test_benchmark_reports_expected_fixture_scenarios(self):
        report = self.run_cli("benchmark", "--repo-root", str(REPO_ROOT), "--json")

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["scenario_ids"], [
            "clean_delivery",
            "missing_review_artifact",
            "stale_lifecycle_filename",
            "mismatched_automation_status",
            "insufficient_verification_evidence",
        ])
        self.assertEqual(report["summary"]["invalid_scenarios"], 4)
        self.assertEqual(report["summary"]["invalid_advancement_caught"], 4)
        self.assertGreaterEqual(report["summary"]["invalid_advancement_caught_by_validation"], 1)
        self.assertEqual(report["summary"]["false_positive_warnings"], 0)
        self.assertTrue(report["summary"]["verification_reproducible"])

        scenarios = self.scenario_by_id(report)
        self.assertEqual(scenarios["clean_delivery"]["validate"]["error_codes"], [])
        self.assertEqual(scenarios["clean_delivery"]["validate"]["warning_codes"], [])
        self.assertIn("review_artifact_missing", self.issue_codes(scenarios["missing_review_artifact"]))
        self.assertIn(
            "roadmap_lifecycle_filename_mismatch",
            scenarios["stale_lifecycle_filename"]["validate"]["error_codes"],
        )
        self.assertIn("automation_status_mismatch", self.issue_codes(scenarios["mismatched_automation_status"]))
        self.assertIn(
            "verification_evidence_missing",
            self.issue_codes(scenarios["insufficient_verification_evidence"]),
        )

    def test_benchmark_can_write_json_report_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "evidence-benchmark.json"
            report = self.run_cli(
                "benchmark",
                "--repo-root",
                str(REPO_ROOT),
                "--output",
                str(output_path),
                "--json",
            )

            self.assertTrue(output_path.exists())
            written = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(written["status"], "passed")
            self.assertEqual(written["summary"], report["summary"])
            self.assertEqual(written["output_path"], str(output_path))


if __name__ == "__main__":
    unittest.main()
