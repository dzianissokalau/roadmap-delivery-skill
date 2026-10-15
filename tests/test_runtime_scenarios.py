"""Mandatory offline acceptance against extracted release contents.

The driver is an isolated host double. It loads only the released runtime;
these tests do not evaluate an agent or contact a real scheduler.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "tests/fixtures/runtime-reliability/scenario_driver.py"
CRASH_POINTS = (
    "after_journal_intent", "after_state_intent", "before_alert", "after_alert", "after_journal_alert", "after_state_alert",
    "before_readback", "after_readback", "after_journal_request", "after_state_request", "before_pause", "after_pause",
    "before_receipt_readback", "after_receipt_readback", "after_journal_receipt", "after_state_receipt", "before_log", "after_log",
)


class RuntimeScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = []
        cls.release = tempfile.TemporaryDirectory(prefix="scenario-releases-")
        proc = subprocess.run([sys.executable, "scripts/build_release.py", "--output-dir", cls.release.name, "--json"],
                              cwd=ROOT, text=True, capture_output=True, timeout=60)
        if proc.returncode:
            cls.release.cleanup()
            raise AssertionError(proc.stdout + proc.stderr)
        cls.archives = {item["kind"]: item["path"] for item in json.loads(proc.stdout)["artifacts"]}

    @classmethod
    def tearDownClass(cls):
        report_path = os.environ.get("RUNTIME_SCENARIO_REPORT")
        if report_path:
            Path(report_path).write_text(json.dumps({"schema_version": 1,
                "evidence_kind": "offline_extracted_release_scheduler_double",
                "real_scheduler": {"status": "skipped", "reason": "No real host effects requested"},
                "independent_agent": {"status": "skipped", "reason": "Independent evaluator unavailable; delegation not authorized"},
                "records": cls.records}, indent=2) + "\n")
        cls.release.cleanup()

    def stage(self, base, host):
        destination = base / "release"
        kind = host + ("_skill_package" if host == "codex" else "_plugin_package")
        shutil.unpack_archive(self.archives[kind], destination)
        package = next(destination.iterdir())
        return package if host == "codex" else package / "skills/roadmap-delivery-skill"

    def run_driver(self, skill, project, *, codes=(0,), **inputs):
        project.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.pop("PYTHONPATH", None); env.pop("PYTHONHOME", None)
        env["HOME"] = str(project / "home")
        env["CODEX_HOME"] = str(project / "home/.codex")
        env["CLAUDE_CONFIG_DIR"] = str(project / "home/.claude")
        env["AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR"] = str(project / "file-runners")
        env["PYTHONNOUSERSITE"] = "1"
        proc = subprocess.run([sys.executable, "-I", "-S", str(DRIVER), str(skill), str(project)],
                              cwd=project, env=env, input=json.dumps(inputs), text=True,
                              capture_output=True, timeout=30)
        record = {"host": "claude" if "/skills/" in str(skill) else "codex", "inputs": inputs,
                  "exit_code": proc.returncode, "expected_exit_codes": list(codes)}
        if proc.returncode:
            record["stderr"] = proc.stderr.replace(str(project), "$PROJECT").replace(str(skill), "$SKILL").replace(str(ROOT), "$REPO_ROOT")
        self.records.append(record)
        self.assertIn(proc.returncode, codes, proc.stdout + proc.stderr)
        if proc.returncode:
            return proc
        result = json.loads(proc.stdout)
        record["result"] = {key: value for key, value in result.items() if key != "origins"}
        self.assertTrue(result["origins"])
        self.assertTrue(all(Path(value).is_relative_to(skill / "runtime") for value in result["origins"].values()))
        self.assertFalse(any(str(ROOT) in value for value in result["origins"].values()))
        return result

    def test_install_to_completion_three_independent_project_roots_per_host(self):
        for host in ("codex", "claude"):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp).resolve(); skill = self.stage(base, host)
                previous = []
                for n in range(3):
                    project = base / f"project-{n}"
                    result = self.run_driver(skill, project, action="full")
                    self.assertEqual(result["state"]["status"], "completed")
                    self.assertEqual(result["state"]["run_count"], 1)
                    self.assertEqual(result["host"]["config"]["cwds"], [str(project)])
                    self.assertEqual(len(result["host"]["requests"]), 1)
                    self.assertEqual(result["state"]["terminal_closeout"]["receipt"]["source"], "offline scenario scheduler double")
                    self.assertEqual((project / "verification.txt").read_text(), "fixture acceptance passed\n")
                    for prior, snapshot, host_snapshot in previous:
                        self.assertEqual((prior / "automation/scenario/delivery_state.json").read_bytes(), snapshot)
                        self.assertEqual((prior / "host.json").read_bytes(), host_snapshot)
                    previous.append((project, (project / "automation/scenario/delivery_state.json").read_bytes(),
                                     (project / "host.json").read_bytes()))
                self.assertEqual(len({json.loads((p / "host.json").read_text())["config"]["target"]["project_id"] for p, _, _ in previous}), 3)

    def test_blocked_run_churn_stops_and_verified_repair_resets_once(self):
        for host in ("codex", "claude"):
            for repair in (False, True):
                with self.subTest(host=host, repair=repair), tempfile.TemporaryDirectory() as tmp:
                    base = Path(tmp).resolve(); skill = self.stage(base, host)
                    result = self.run_driver(skill, base / "project", action="blockers", repair=repair)
                    self.assertEqual(result["state"]["run_count"], 3 if repair else 2)
                    self.assertEqual(result["state"]["stalled_run_count"], 1 if repair else 2)
                    self.assertEqual(len(result["host"]["requests"]), 0 if repair else 1)

    def test_partial_writes_duplicate_run_ids_and_concurrent_stale_plans(self):
        for host in ("codex", "claude"):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp).resolve(); skill = self.stage(base, host)
                self.run_driver(skill, base / "project", action="journal")

    def test_pause_policy_cross_product_in_released_entrypoints(self):
        for host in ("codex", "claude"):
            with tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp).resolve(); skill = self.stage(base, host)
                for mode in ("missing", "conservative", "delegated_local", "delegated_delivery", "custom"):
                    for stalled in (False, True):
                        for optout in ((False,) if mode == "missing" else (False, True)):
                            with self.subTest(host=host, mode=mode, stalled=stalled, optout=optout):
                                self.run_driver(skill, base / f"{mode}-{stalled}-{optout}", action="policy",
                                                mode=mode, stalled=stalled, optout=optout)

    def test_each_closeout_effect_recovers_across_process_restart(self):
        for host in ("codex", "claude"):
            with tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp).resolve(); skill = self.stage(base, host)
                for point in CRASH_POINTS:
                    with self.subTest(host=host, point=point):
                        project = base / point
                        self.run_driver(skill, project, action="prepare-terminal")
                        failed = self.run_driver(skill, project, action="closeout", failpoint=point, codes=(1,))
                        self.assertIn("scenario-crash:" + point, failed.stderr)
                        result = self.run_driver(skill, project, action="closeout")
                        self.assertTrue(result["completion_claim"])
                        state_path = project / "automation/scenario/delivery_state.json"
                        before = json.loads(state_path.read_text())
                        repeat = self.run_driver(skill, project, action="closeout")
                        self.assertTrue(repeat["completion_claim"])
                        self.assertEqual(json.loads(state_path.read_text())["run_count"], before["run_count"])
                        host_data = json.loads((project / "host.json").read_text())
                        self.assertEqual(len(host_data["requests"]), 1)
                        self.assertEqual(len(list((project / "automation/scenario/alerts").glob("*.md"))), 1)

    def test_closeout_ack_loss_and_transient_rejections_never_fabricate_receipts(self):
        for host in ("codex", "claude"):
            with tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp).resolve(); skill = self.stage(base, host)
                for failure in ("lose_ack", "reject"):
                    project = base / failure
                    self.run_driver(skill, project, action="prepare-terminal")
                    first = self.run_driver(skill, project, action="closeout", **{failure: True})
                    self.assertFalse(first["completion_claim"]); self.assertIsNone(first["receipt"])
                    if failure == "lose_ack":
                        self.assertTrue(self.run_driver(skill, project, action="closeout")["completion_claim"])
                    else:
                        for _ in range(3):
                            result = self.run_driver(skill, project, action="closeout", reject=True)
                        self.assertEqual(result["status"], "retry_exhausted")
                    data = json.loads((project / "host.json").read_text())
                    self.assertEqual(len(data["requests"]), 1 if failure == "lose_ack" else 2)

    def test_six_regressions_pass_and_old_behavior_mutants_are_detected(self):
        for host in ("codex", "claude"):
            with tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp).resolve(); skill = self.stage(base, host)
                for regression in ("R1", "R3", "R4", "R5", "R6"):
                    with self.subTest(host=host, regression=regression):
                        self.run_driver(skill, base / (regression + "-passing"), action="regression", regression=regression)
                        failed = self.run_driver(skill, base / (regression + "-mutant"), action="regression", regression=regression, mutate=True, codes=(1,))
                        self.assertIn("regression-probe:" + regression + ":", failed.stderr)
                # R2's actual historical defect is a package without its runtime.
                project = base / "R2"; project.mkdir()
                for helper in ("validate_delivery_artifacts.py", "compute_progress_signature.py"):
                    proc = subprocess.run([sys.executable, "-I", "-S", str(skill / "scripts" / helper), "--help"],
                                          cwd=project, capture_output=True, text=True, timeout=30)
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                shutil.rmtree(skill / "runtime")
                for helper in ("validate_delivery_artifacts.py", "compute_progress_signature.py"):
                    proc = subprocess.run([sys.executable, "-I", "-S", str(skill / "scripts" / helper), "--help"],
                                          cwd=project, capture_output=True, text=True, timeout=30)
                    self.assertEqual(proc.returncode, 2)
                    self.assertIn("reinstall", proc.stderr)
                self.records.append({"host": host, "inputs": {"action": "regression", "regression": "R2"},
                    "baseline_exit_codes": [0, 0], "mutant_exit_codes": [2, 2],
                    "mutant_kind": "released runtime removed", "diagnostic": "reinstall required"})

    @unittest.skip("Independent fresh-context skill evaluation unavailable in the offline harness; no agent delegation authorized")
    def test_independent_fresh_context_skill_evaluation(self):
        """Raw realistic requests are in fixtures/runtime-reliability/skill-evaluation.json."""


if __name__ == "__main__":
    unittest.main()
