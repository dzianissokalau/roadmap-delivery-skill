import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = REPO_ROOT / "examples" / "demo-roadmap"
DEMO_SLUG = "demo-roadmap"
DEMO_AUTOMATION_ID = "demo-roadmap-delivery"


class DemoSmokeTests(unittest.TestCase):
    maxDiff = None

    def run_cli(self, *args, env=None, allowed_returncodes=(0,)):
        proc = subprocess.run(
            [sys.executable, "-m", "roadmap_delivery.cli", *args],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )
        self.assertIn(proc.returncode, allowed_returncodes, proc.stderr or proc.stdout)
        return json.loads(proc.stdout)

    def copy_demo_repo(self, tmpdir):
        demo_repo = Path(tmpdir) / "demo-roadmap"
        shutil.copytree(DEMO_ROOT, demo_repo)
        subprocess.run(
            ["git", "init", "-b", "codex/demo-roadmap-phase-1"],
            cwd=demo_repo,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(["git", "add", "."], cwd=demo_repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Demo",
                "-c",
                "user.email=demo.invalid",
                "commit",
                "-m",
                "demo fixture",
            ],
            cwd=demo_repo,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return demo_repo

    def env_with_config(self, tmpdir, demo_repo, source):
        home = Path(tmpdir) / "home"
        automation_dir = home / ".codex" / "automations" / DEMO_AUTOMATION_ID
        automation_dir.mkdir(parents=True)
        env = os.environ.copy()
        env["HOME"] = str(home)
        env["AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR"] = str(home / ".codex" / "automations")
        env["PYTHONPYCACHEPREFIX"] = str(Path(tmpdir) / "pycache")
        self.write_demo_config(env, demo_repo, source)
        return env

    def write_demo_config(self, env, demo_repo, source):
        automation_dir = Path(env["AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR"]) / DEMO_AUTOMATION_ID
        automation_dir.mkdir(parents=True, exist_ok=True)
        text = source.read_text(encoding="utf-8")
        text = text.replace('cwds = ["."]', "cwds = [" + json.dumps(str(demo_repo)) + "]")
        (automation_dir / "automation.toml").write_text(text, encoding="utf-8")

    def apply_blocked_scenario(self, demo_repo):
        scenario = DEMO_ROOT / "scenarios" / "blocked-remediation"
        state_dir = demo_repo / "automation" / "demo_roadmap"
        shutil.copy2(scenario / "delivery_state.json", state_dir / "delivery_state.json")
        shutil.copy2(scenario / "review_fix_state.json", state_dir / "review_fix_state.json")
        shutil.copy2(
            scenario / "demo-roadmap-phase-1-review-iteration-1.md",
            state_dir / "reviews" / "demo-roadmap-phase-1-review-iteration-1.md",
        )
        subprocess.run(["git", "add", "."], cwd=demo_repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Demo",
                "-c",
                "user.email=demo.invalid",
                "commit",
                "-m",
                "blocked scenario",
            ],
            cwd=demo_repo,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def warning_codes(self, report):
        return {item["code"] for item in report.get("warnings", [])}

    def error_codes(self, report):
        return {item["code"] for item in report.get("errors", [])}

    def test_demo_records_one_delivered_phase_loop(self):
        state = json.loads((DEMO_ROOT / "automation" / "demo_roadmap" / "delivery_state.json").read_text(encoding="utf-8"))
        log = (DEMO_ROOT / "automation" / "demo_roadmap" / "delivery_log.md").read_text(encoding="utf-8")
        review = (DEMO_ROOT / "automation" / "demo_roadmap" / "reviews" / "demo-roadmap-phase-0-review-iteration-1.md").read_text(encoding="utf-8")

        self.assertEqual(state["last_delivered_phase"], "Phase 0 - Establish Fixture Contract")
        self.assertEqual(state["current_phase"], "Phase 1 - Add Smoke Checked Command")
        self.assertEqual(state["last_review"]["verdict"], "delivered")
        self.assertIn("Status: delivered", log)
        self.assertIn("Verdict: delivered", review)

    def test_scaffold_dry_run_for_demo_slug_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "empty-repo"
            repo_root.mkdir()

            report = self.run_cli(
                "scaffold",
                "--repo-root",
                str(repo_root),
                "--roadmap-slug",
                DEMO_SLUG,
                "--automation-id",
                DEMO_AUTOMATION_ID,
                "--dry-run",
                "--json",
            )

            self.assertEqual(report["status"], "ok")
            self.assertTrue(report["dry_run"])
            self.assertIn(str(repo_root.resolve() / "automation" / "demo_roadmap"), report["would_create"])
            self.assertFalse((repo_root / "automation" / "demo_roadmap").exists())

    def test_demo_fixture_validates_and_inspects_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo_repo = self.copy_demo_repo(tmp)
            env = self.env_with_config(
                tmp,
                demo_repo,
                DEMO_ROOT / "automation-config" / DEMO_AUTOMATION_ID / "automation.toml",
            )

            validate = self.run_cli(
                "validate",
                "--repo-root",
                str(demo_repo),
                "--roadmap-slug",
                DEMO_SLUG,
                "--automation-id",
                DEMO_AUTOMATION_ID,
                "--strict",
                "--json",
                env=env,
            )
            inspect = self.run_cli(
                "inspect",
                "--repo-root",
                str(demo_repo),
                "--roadmap-slug",
                DEMO_SLUG,
                "--automation-id",
                DEMO_AUTOMATION_ID,
                "--strict",
                "--json",
                env=env,
            )

            self.assertEqual(validate["status"], "ok")
            self.assertEqual(validate["errors"], [])
            self.assertEqual(validate["warnings"], [])
            self.assertEqual(inspect["status"], "ok")
            self.assertEqual(inspect["current_phase"], "Phase 1 - Add Smoke Checked Command")
            self.assertEqual(inspect["last_delivered_phase"], "Phase 0 - Establish Fixture Contract")
            self.assertTrue(inspect["blocked_remediation_guard"])
            self.assertEqual(inspect["required_model"], "gpt-5.5")
            self.assertEqual(inspect["required_reasoning_effort"], "xhigh")
            self.assertEqual(inspect["configured_automation_model"], "gpt-5.5")
            self.assertEqual(inspect["configured_automation_reasoning_effort"], "xhigh")
            self.assertIn("write_state_log_review_artifacts", inspect["allowed_operations"])
            self.assertFalse(inspect["blocked_remediation_required"])

    def test_blocked_remediation_scenario_reports_guarded_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo_repo = self.copy_demo_repo(tmp)
            self.apply_blocked_scenario(demo_repo)
            env = self.env_with_config(
                tmp,
                demo_repo,
                DEMO_ROOT / "automation-config" / DEMO_AUTOMATION_ID / "automation.toml",
            )

            inspect = self.run_cli(
                "inspect",
                "--repo-root",
                str(demo_repo),
                "--roadmap-slug",
                DEMO_SLUG,
                "--automation-id",
                DEMO_AUTOMATION_ID,
                "--json",
                env=env,
            )
            validate = self.run_cli(
                "validate",
                "--repo-root",
                str(demo_repo),
                "--roadmap-slug",
                DEMO_SLUG,
                "--automation-id",
                DEMO_AUTOMATION_ID,
                "--json",
                env=env,
            )

            self.assertTrue(inspect["blocked_remediation_required"])
            self.assertTrue(inspect["blocked_remediation_guard"])
            self.assertIn("demo_tool/status.py", inspect["blocked_reason"])
            self.assertEqual(validate["errors"], [])
            self.assertIn("blocked_state_missing_operator_alert", self.warning_codes(validate))

    def test_model_policy_mismatch_scenario_blocks_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo_repo = self.copy_demo_repo(tmp)
            env = self.env_with_config(
                tmp,
                demo_repo,
                DEMO_ROOT / "scenarios" / "model-policy-mismatch" / "automation.toml",
            )

            validate = self.run_cli(
                "validate",
                "--repo-root",
                str(demo_repo),
                "--roadmap-slug",
                DEMO_SLUG,
                "--automation-id",
                DEMO_AUTOMATION_ID,
                "--json",
                env=env,
                allowed_returncodes=(1,),
            )
            inspect = self.run_cli(
                "inspect",
                "--repo-root",
                str(demo_repo),
                "--roadmap-slug",
                DEMO_SLUG,
                "--automation-id",
                DEMO_AUTOMATION_ID,
                "--json",
                env=env,
            )

            self.assertIn("automation_model_mismatch", self.error_codes(validate))
            self.assertIn("automation_reasoning_mismatch", self.error_codes(validate))
            self.assertIn("automation_model_mismatch", self.warning_codes(inspect))
            self.assertIn("automation_reasoning_mismatch", self.warning_codes(inspect))

    def test_policy_mismatch_demo_remediates_with_temp_config_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo_repo = self.copy_demo_repo(tmp)
            env = self.env_with_config(
                tmp,
                demo_repo,
                DEMO_ROOT / "scenarios" / "model-policy-mismatch" / "automation.toml",
            )

            blocked = self.run_cli(
                "validate",
                "--repo-root",
                str(demo_repo),
                "--roadmap-slug",
                DEMO_SLUG,
                "--automation-id",
                DEMO_AUTOMATION_ID,
                "--json",
                env=env,
                allowed_returncodes=(1,),
            )
            blocked_inspect = self.run_cli(
                "inspect",
                "--repo-root",
                str(demo_repo),
                "--roadmap-slug",
                DEMO_SLUG,
                "--automation-id",
                DEMO_AUTOMATION_ID,
                "--json",
                env=env,
            )

            self.assertIn("automation_model_mismatch", self.error_codes(blocked))
            self.assertIn("automation_reasoning_mismatch", self.error_codes(blocked))
            self.assertTrue(blocked_inspect["model_mismatch"])
            self.assertFalse(blocked_inspect["reasoning_satisfied"])

            self.write_demo_config(
                env,
                demo_repo,
                DEMO_ROOT / "automation-config" / DEMO_AUTOMATION_ID / "automation.toml",
            )

            repaired = self.run_cli(
                "validate",
                "--repo-root",
                str(demo_repo),
                "--roadmap-slug",
                DEMO_SLUG,
                "--automation-id",
                DEMO_AUTOMATION_ID,
                "--strict",
                "--json",
                env=env,
            )
            repaired_inspect = self.run_cli(
                "inspect",
                "--repo-root",
                str(demo_repo),
                "--roadmap-slug",
                DEMO_SLUG,
                "--automation-id",
                DEMO_AUTOMATION_ID,
                "--strict",
                "--json",
                env=env,
            )

            self.assertEqual(repaired["status"], "ok")
            self.assertEqual(repaired["errors"], [])
            self.assertEqual(repaired["warnings"], [])
            self.assertEqual(repaired_inspect["status"], "ok")
            self.assertFalse(repaired_inspect["model_mismatch"])
            self.assertTrue(repaired_inspect["reasoning_satisfied"])
            self.assertFalse(repaired_inspect["blocked_remediation_required"])


if __name__ == "__main__":
    unittest.main()
