import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class OnboardingWizardTests(unittest.TestCase):
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
        return proc

    def env_for(self, tmp):
        env = os.environ.copy()
        env["AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR"] = str(Path(tmp) / "home" / "automations")
        return env

    def test_wizard_dry_run_plans_repository_local_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()

            proc = self.run_cli(
                "wizard",
                "--repo-root",
                str(repo_root),
                "--roadmap-slug",
                "pilot-roadmap",
                "--automation-id",
                "pilot-roadmap-delivery",
                "--json",
                env=self.env_for(tmp),
            )
            report = json.loads(proc.stdout)

            self.assertEqual(report["command"], "wizard")
            self.assertEqual(report["status"], "planned")
            self.assertTrue(report["dry_run"])
            self.assertEqual(report["approval_mode"], "conservative")
            self.assertEqual(report["model_policy"]["default_model"], "gpt-5.5")
            self.assertEqual(report["model_policy"]["default_reasoning_effort"], "xhigh")
            self.assertEqual(report["setup_choices"]["max_stalled_runs"], 2)
            self.assertTrue(report["setup_choices"]["pause_automation_on_completion"])
            self.assertTrue(report["setup_choices"]["pause_automation_on_stall"])
            self.assertFalse(report["live_automation"]["created"])
            self.assertIn(str(repo_root.resolve() / "automation" / "pilot_roadmap" / "delivery_state.json"), report["would_create"])
            self.assertEqual(report["planned_create"], report["would_create"])
            self.assertIn(str(repo_root.resolve() / "automation" / "pilot_roadmap" / "delivery_state.json"), report["artifact_groups"]["automation"])
            self.assertIn(str(repo_root.resolve() / "automation" / "pilot_roadmap" / "automation_guide.md"), report["artifact_groups"]["docs"])
            self.assertFalse(report["readback"]["ran"])
            self.assertIn("validate", report["next_commands"][0])
            self.assertIn("worktree_dirty", report["next_commands"][0])
            self.assertFalse((repo_root / "automation" / "pilot_roadmap").exists())

    def test_wizard_write_mode_creates_immediately_valid_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

            dry_run = self.run_cli(
                "wizard",
                "--repo-root",
                str(repo_root),
                "--roadmap-slug",
                "pilot-roadmap",
                "--automation-id",
                "pilot-roadmap-delivery",
                "--roadmap-title",
                "Pilot Roadmap",
                "--dry-run",
                "--json",
                env=self.env_for(tmp),
            )
            dry_report = json.loads(dry_run.stdout)
            proc = self.run_cli(
                "wizard",
                "--repo-root",
                str(repo_root),
                "--roadmap-slug",
                "pilot-roadmap",
                "--automation-id",
                "pilot-roadmap-delivery",
                "--roadmap-title",
                "Pilot Roadmap",
                "--write",
                "--json",
                env=self.env_for(tmp),
            )
            report = json.loads(proc.stdout)

            automation_dir = repo_root / "automation" / "pilot_roadmap"
            self.assertEqual(report["status"], "written")
            self.assertEqual(sorted(dry_report["would_create"]), sorted(report["created"]))
            self.assertTrue(report["readback"]["ran"])
            self.assertEqual(report["readback"]["validate"]["errors"], [])
            self.assertEqual(report["readback"]["inspect"]["errors"], [])
            self.assertIn("missing_automation_config", report["readback"]["validate"]["warning_codes"])
            self.assertFalse(report["live_automation"]["created"])
            self.assertTrue((repo_root / "roadmaps" / "not_started_pilot_roadmap_roadmap.md").is_file())
            self.assertTrue((automation_dir / "automation_guide.md").is_file())
            self.assertTrue((automation_dir / "approval_policy.json").is_file())
            self.assertTrue((automation_dir / "phase_model_policy.json").is_file())
            self.assertTrue((automation_dir / "reviews" / ".gitkeep").is_file())
            policy = json.loads((automation_dir / "approval_policy.json").read_text(encoding="utf-8"))
            model_policy = json.loads((automation_dir / "phase_model_policy.json").read_text(encoding="utf-8"))
            state = json.loads((automation_dir / "delivery_state.json").read_text(encoding="utf-8"))
            self.assertTrue(policy["pause_automation_on_completion"])
            self.assertTrue(policy["pause_automation_on_stall"])
            self.assertEqual(model_policy["max_stalled_runs"], 2)
            self.assertEqual(state["max_stalled_runs"], 2)

            validate = self.run_cli(
                "validate",
                "--repo-root",
                str(repo_root),
                "--roadmap-slug",
                "pilot-roadmap",
                "--automation-id",
                "pilot-roadmap-delivery",
                "--strict",
                "--allow-warning",
                "missing_automation_config",
                "--allow-warning",
                "current_branch_name_mismatch",
                "--allow-warning",
                "empty_review_dir",
                "--allow-warning",
                "worktree_dirty",
                "--json",
                env=self.env_for(tmp),
            )
            validate_report = json.loads(validate.stdout)

            self.assertEqual(validate_report["status"], "warning")
            self.assertEqual(validate_report["errors"], [])

    def test_wizard_delegated_mode_is_explicit_and_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()

            proc = self.run_cli(
                "wizard",
                "--repo-root",
                str(repo_root),
                "--roadmap-slug",
                "delegated-roadmap",
                "--approval-mode",
                "delegated_local",
                "--dry-run",
                "--json",
                env=self.env_for(tmp),
            )
            report = json.loads(proc.stdout)
            operations = report["approval_policy"]["policy"]["operations"]

            self.assertEqual(report["approval_mode"], "delegated_local")
            self.assertTrue(operations["commit_delivered_phase_locally"])
            self.assertTrue(operations["retarget_saved_automation"])
            self.assertTrue(operations["pause_saved_automation"])
            self.assertFalse(operations["push_current_phase_branch"])

    def test_wizard_can_override_safety_pause_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()

            proc = self.run_cli(
                "wizard",
                "--repo-root",
                str(repo_root),
                "--roadmap-slug",
                "pilot-roadmap",
                "--max-stalled-runs",
                "4",
                "--no-pause-on-completion",
                "--no-pause-on-stall",
                "--dry-run",
                "--json",
                env=self.env_for(tmp),
            )
            report = json.loads(proc.stdout)

            self.assertEqual(report["setup_choices"]["max_stalled_runs"], 4)
            self.assertFalse(report["setup_choices"]["pause_automation_on_completion"])
            self.assertFalse(report["setup_choices"]["pause_automation_on_stall"])
            self.assertIn("pause_automation_on_completion_reason", report["approval_policy"]["policy"])
            self.assertIn("pause_automation_on_stall_reason", report["approval_policy"]["policy"])
            self.assertEqual(report["model_policy"]["policy"]["max_stalled_runs"], 4)

    def test_wizard_write_refuses_existing_artifacts_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            roadmap_dir = repo_root / "roadmaps"
            roadmap_dir.mkdir(parents=True)
            (roadmap_dir / "not_started_pilot_roadmap_roadmap.md").write_text("existing\n", encoding="utf-8")

            proc = self.run_cli(
                "wizard",
                "--repo-root",
                str(repo_root),
                "--roadmap-slug",
                "pilot-roadmap",
                "--write",
                "--json",
                env=self.env_for(tmp),
                allowed_returncodes=(1,),
            )
            report = json.loads(proc.stdout)

            self.assertEqual(report["status"], "error")
            self.assertEqual(report["errors"][0]["code"], "wizard_existing_artifacts")

    def test_wizard_refuses_roadmap_paths_outside_repo_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            outside_path = Path(tmp) / "outside-roadmap.md"

            proc = self.run_cli(
                "wizard",
                "--repo-root",
                str(repo_root),
                "--roadmap-slug",
                "pilot-roadmap",
                "--roadmap-path",
                str(outside_path),
                "--write",
                "--json",
                env=self.env_for(tmp),
                allowed_returncodes=(1,),
            )
            report = json.loads(proc.stdout)

            self.assertEqual(report["status"], "error")
            self.assertEqual(report["errors"][0]["code"], "path_outside_repo_root")
            self.assertFalse(outside_path.exists())

    def test_wizard_write_fails_when_generated_artifacts_do_not_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

            proc = self.run_cli(
                "wizard",
                "--repo-root",
                str(repo_root),
                "--roadmap-slug",
                "pilot-roadmap",
                "--initial-model",
                "",
                "--write",
                "--json",
                env=self.env_for(tmp),
                allowed_returncodes=(1,),
            )
            report = json.loads(proc.stdout)
            readback_error_codes = {item["code"] for item in report["readback"]["validate"]["errors"]}

            self.assertEqual(report["status"], "error")
            self.assertTrue(report["readback"]["ran"])
            self.assertIn("wizard_readback_failed", {item["code"] for item in report["errors"]})
            self.assertIn("missing_default_model", readback_error_codes)


if __name__ == "__main__":
    unittest.main()
