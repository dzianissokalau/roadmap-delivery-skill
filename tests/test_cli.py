import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from tests.test_helper_scripts import DeliveryFixture, VALIDATE_SCRIPT
except ModuleNotFoundError:
    from test_helper_scripts import DeliveryFixture, VALIDATE_SCRIPT


REPO_ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
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

    def test_version_runs_from_source_tree(self):
        proc = self.run_cli("version")

        version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(proc.stdout.strip(), f"roadmap-delivery {version}")

    def test_plan_migration_exact_diff_is_read_only_and_missing_policy_is_visible(self):
        from tests.test_runtime_migrations import CONFIG, EXPECTED, POLICY, ROADMAP
        from roadmap_delivery.automation import runner_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot, expected, policy = [root / name for name in ("runner.json", "expected.json", "policy.json")]
            snapshot.write_text(json.dumps(runner_snapshot(CONFIG, source="offline fixture")))
            expected.write_text(json.dumps(EXPECTED)); policy.write_text(json.dumps(POLICY))
            before = {p.name:p.read_bytes() for p in root.iterdir()}
            common = ("plan-migration", "--roadmap-slug", "fixture", "--roadmap-path", ROADMAP,
                      "--runner-snapshot", str(snapshot), "--expected-file", str(expected), "--json")
            result = json.loads(self.run_cli(*common, "--policy-file", str(policy)).stdout)
            self.assertEqual(result["status"], "planned")
            self.assertEqual(result["effects"], ["update_prompt_only"])
            self.assertTrue(result["read_only"])
            self.assertIn("before/prompt", result["diffs"]["prompt"])
            missing = json.loads(self.run_cli(*common, allowed_returncodes=(2,)).stdout)
            self.assertIn("missing_policy", missing["issues"])
            self.assertEqual(before, {p.name:p.read_bytes() for p in root.iterdir()})
            policy.write_text("not JSON")
            bad = json.loads(self.run_cli(*common, "--policy-file", str(policy), allowed_returncodes=(2,)).stdout)
            self.assertEqual(bad["status"], "needs-decision")

    def test_plan_control_terminal_exit_categories_and_no_mutations(self):
        from tests.test_runtime_control import runner, phase_state, final_evidence
        from roadmap_delivery.approval import default_approval_policy
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); directory = root / "automation/fixture"; directory.mkdir(parents=True)
            state_file = directory / "delivery_state.json"
            snapshot = root / "runner.json"; evidence = root / "evidence.json"
            evidence.write_text(json.dumps(final_evidence()))
            cases = (
                ("completed", default_approval_policy(), runner(), "ready", 0),
                ("completed", default_approval_policy(pause_on_completion=False), runner(), "disabled", 0),
                ("completed", default_approval_policy(), {**runner(), "capabilities": {}}, "unsupported", 3),
                ("completed", {}, runner(), "invalid_input", 2),
                ("not_started", default_approval_policy("custom", {"edit_phase_owned_files": False}), runner(), "permission_required", 1),
            )
            for status, policy, observed, result, code in cases:
                state_file.write_text(json.dumps(phase_state(status=status)))
                (directory / "approval_policy.json").write_text(json.dumps(policy))
                snapshot.write_text(json.dumps(observed))
                before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
                proc = self.run_cli("plan-control", "--repo-root", str(root), "--roadmap-slug", "fixture",
                                    "--evidence-file", str(evidence), "--runner-snapshot", str(snapshot), "--json", allowed_returncodes=(code,))
                report = json.loads(proc.stdout)
                self.assertEqual(report["result"], result)
                self.assertEqual(report["exit_code"], code)
                self.assertEqual(before, {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()})

    def test_plan_control_missing_input_returns_stable_invalid_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_cli("plan-control", "--repo-root", tmp, "--roadmap-slug", "missing", "--json", allowed_returncodes=(2,))
            self.assertEqual(json.loads(proc.stdout)["result"], "invalid_input")

    def test_plan_control_invalid_model_policy_blocks_only_phase_work(self):
        from tests.test_runtime_control import runner, phase_state, final_evidence
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); directory = root / "automation/fixture"; directory.mkdir(parents=True)
            snapshot = root / "runner.json"; snapshot.write_text(json.dumps(runner()))
            evidence = root / "evidence.json"; evidence.write_text(json.dumps({**final_evidence(), "prerequisites_passed": True}))
            (directory / "phase_model_policy.json").write_text(json.dumps({"schema_version": 999, "defaults": {"model": "fixture-model", "reasoning_effort": "high"}, "phases": {}}))
            for status, code, action in (("not_started", 2, "block_phase_work"), ("completed", 0, "pause_status_only")):
                (directory / "delivery_state.json").write_text(json.dumps(phase_state(status=status)))
                proc = self.run_cli("plan-control", "--repo-root", str(root), "--roadmap-slug", "fixture", "--evidence-file", str(evidence), "--runner-snapshot", str(snapshot), "--json", allowed_returncodes=(code,))
                report = json.loads(proc.stdout)
                self.assertEqual(report["action"], action)
                self.assertTrue(report["prerequisite_errors"])

    def test_validate_strict_returns_nonzero_on_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()

            proc = self.run_cli(
                "validate",
                "--repo-root",
                str(repo_root),
                "--roadmap-slug",
                "missing-roadmap",
                "--strict",
                "--json",
                allowed_returncodes=(1,),
            )
            report = json.loads(proc.stdout)

            self.assertEqual(report["status"], "error")
            self.assertEqual(report["errors"][0]["code"], "missing_state_file")

    def test_validate_uses_same_report_as_helper_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_model_policy=True)

            cli = self.run_cli(
                "validate",
                "--repo-root",
                str(fixture.repo_root),
                "--roadmap-slug",
                fixture.slug,
                "--automation-id",
                fixture.automation_id,
                "--json",
                env=fixture.env(),
            )
            helper = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATE_SCRIPT),
                    "--repo-root",
                    str(fixture.repo_root),
                    "--roadmap-slug",
                    fixture.slug,
                    "--automation-id",
                    fixture.automation_id,
                    "--json",
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=fixture.env(),
                check=False,
            )
            self.assertEqual(helper.returncode, 0, helper.stderr or helper.stdout)
            cli_report = json.loads(cli.stdout)
            helper_report = json.loads(helper.stdout)

            self.assertEqual(cli_report["command"], "validate")
            self.assertEqual(cli_report["cli_schema_version"], 1)
            self.assertEqual(cli_report["status"], "ok")
            self.assertEqual(cli_report["errors"], helper_report["errors"])
            self.assertEqual(cli_report["warnings"], helper_report["warnings"])
            self.assertEqual(cli_report["state_current_phase"], helper_report["state_current_phase"])

    def test_inspect_json_has_stable_cli_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_model_policy=True)

            proc = self.run_cli(
                "inspect",
                "--repo-root",
                str(fixture.repo_root),
                "--roadmap-slug",
                fixture.slug,
                "--automation-id",
                fixture.automation_id,
                "--json",
                env=fixture.env(),
            )
            report = json.loads(proc.stdout)

            self.assertEqual(report["command"], "inspect")
            self.assertEqual(report["cli_schema_version"], 1)
            self.assertEqual(report["status"], "ok")
            self.assertEqual(report["current_phase"], "Phase 1 - Fixture")
            self.assertEqual(report["required_model"], "gpt-5.5")

    def test_inspect_uses_fresh_capability_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_model_policy=True)
            policy_file = fixture.state_dir / "phase_model_policy.json"
            policy = json.loads(policy_file.read_text())
            policy["adaptive_model_policy"] = {"enabled": False, "caps": {
                "allowed_models": ["gpt-5.5"], "allowed_providers": ["approved-vendor"]}}
            policy_file.write_text(json.dumps(policy))
            metadata_file = Path(tmp) / "capabilities.json"
            metadata = {"trusted": True, "source": "offline-adapter", "models": {
                "gpt-5.5": {"provider": "approved-vendor", "reasoning_efforts": ["xhigh"]}}}
            common = ("--repo-root", str(fixture.repo_root), "--roadmap-slug", fixture.slug,
                      "--automation-id", fixture.automation_id, "--capabilities-file", str(metadata_file), "--json")
            for provider, expected_status in (("approved-vendor", "resolved"), ("revoked-vendor", "invalid_policy")):
                with self.subTest(provider=provider):
                    metadata["models"]["gpt-5.5"]["provider"] = provider
                    metadata_file.write_text(json.dumps(metadata))
                    inspected = json.loads(self.run_cli("inspect", *common, env=fixture.env(), allowed_returncodes=(0, 1)).stdout)
                    validated = json.loads(self.run_cli("validate", *common, env=fixture.env(), allowed_returncodes=(0, 1)).stdout)
                    resolution = inspected["model_policy"]["target_resolution"]
                    self.assertEqual(resolution["status"], expected_status)
                    self.assertEqual(resolution, validated["model_policy"]["target_resolution"])

    def test_terminal_closeout_loads_external_outcome_without_applying_it(self):
        from roadmap_delivery.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = root / "runner.json"
            snapshot.write_text(json.dumps({"source": "offline-adapter", "status": "ACTIVE"}))
            outcome_file = root / "outcome.json"
            outcome = {"request_id": "fixture-request", "attempt": 1,
                       "status": "transient_failure", "source": "offline-adapter"}
            outcome_file.write_text(json.dumps(outcome))
            args = ["terminal-closeout", "--repo-root", str(root), "--state-file", "state.json",
                    "--runner-snapshot", str(snapshot), "--external-outcome", str(outcome_file), "--json"]
            with patch("roadmap_delivery.automation.resume_terminal_closeout", return_value={"exit_code": 4}) as resume:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(args), 4)
                resume.assert_called_once_with(root.resolve(), root.resolve() / "state.json",
                    observed={"source": "offline-adapter", "status": "ACTIVE"}, external_outcome=outcome)
            outcome_file.write_text("[]")
            with patch("roadmap_delivery.automation.resume_terminal_closeout") as resume:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(args), 2)
                self.assertEqual(json.loads(output.getvalue())["result"], "invalid_input")
                resume.assert_not_called()

    def test_scaffold_dry_run_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()

            proc = self.run_cli(
                "scaffold",
                "--repo-root",
                str(repo_root),
                "--roadmap-slug",
                "new-roadmap",
                "--automation-id",
                "new-roadmap-delivery",
                "--dry-run",
                "--json",
            )
            report = json.loads(proc.stdout)

            self.assertTrue(report["dry_run"])
            self.assertEqual(report["command"], "scaffold")
            self.assertIn(str(repo_root.resolve() / "automation" / "new_roadmap"), report["would_create"])
            self.assertIn(str(repo_root.resolve() / "automation" / "new_roadmap" / "approval_policy.json"), report["would_create"])
            self.assertEqual(report["approval_policy"]["approval_mode"], "conservative")
            self.assertEqual(
                report["approval_policy"]["approved_operations"],
                [
                    "edit_phase_owned_files",
                    "write_state_log_review_artifacts",
                    "create_or_switch_phase_branch",
                    "run_verification",
                ],
            )
            self.assertTrue(report["approval_policy"]["policy"]["pause_automation_on_completion"])
            self.assertTrue(report["approval_policy"]["policy"]["pause_automation_on_stall"])
            self.assertEqual(report["model_policy"]["policy"]["max_stalled_runs"], 2)
            self.assertFalse((repo_root / "automation" / "new_roadmap").exists())

    def test_scaffold_write_mode_creates_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()

            proc = self.run_cli(
                "scaffold",
                "--repo-root",
                str(repo_root),
                "--roadmap-slug",
                "new-roadmap",
                "--automation-id",
                "new-roadmap-delivery",
                "--json",
            )
            report = json.loads(proc.stdout)

            automation_dir = repo_root / "automation" / "new_roadmap"
            self.assertFalse(report["dry_run"])
            self.assertTrue((repo_root / "roadmaps" / "not_started_new_roadmap_roadmap.md").is_file())
            self.assertTrue((automation_dir / "approval_policy.json").is_file())
            self.assertTrue((automation_dir / "delivery_state.json").is_file())
            self.assertTrue((automation_dir / "reviews").is_dir())
            policy = json.loads((automation_dir / "approval_policy.json").read_text(encoding="utf-8"))
            model_policy = json.loads((automation_dir / "phase_model_policy.json").read_text(encoding="utf-8"))
            state = json.loads((automation_dir / "delivery_state.json").read_text(encoding="utf-8"))
            self.assertEqual(policy["approval_mode"], "conservative")
            self.assertTrue(policy["pause_automation_on_completion"])
            self.assertTrue(policy["pause_automation_on_stall"])
            self.assertFalse(model_policy["adaptive_model_policy"]["enabled"])
            self.assertEqual(model_policy["max_stalled_runs"], 2)
            self.assertEqual(state["roadmap_slug"], "new-roadmap")
            self.assertEqual(state["approval_policy_path"], "automation/new_roadmap/approval_policy.json")
            self.assertEqual(state["approval_mode"], "conservative")
            self.assertEqual(state["max_stalled_runs"], 2)
            self.assertTrue(state["last_approval_policy_readback"]["pause_automation_on_completion"])
            self.assertTrue(state["last_approval_policy_readback"]["pause_automation_on_stall"])
            self.assertEqual(state["last_approval_policy_readback"]["status"], "valid")
            self.assertIsNone(state["last_run_quality"])
            self.assertEqual(state["adaptive_flawless_streak"], 0)
            self.assertIn(str((automation_dir / "delivery_state.json").resolve()), report["created"])

    def test_scaffold_can_disable_safety_pauses_and_change_stall_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()

            proc = self.run_cli(
                "scaffold",
                "--repo-root",
                str(repo_root),
                "--roadmap-slug",
                "new-roadmap",
                "--max-stalled-runs",
                "5",
                "--no-pause-on-completion",
                "--no-pause-on-stall",
                "--dry-run",
                "--json",
            )
            report = json.loads(proc.stdout)
            policy = report["approval_policy"]["policy"]

            self.assertEqual(report["model_policy"]["policy"]["max_stalled_runs"], 5)
            self.assertFalse(policy["pause_automation_on_completion"])
            self.assertFalse(policy["pause_automation_on_stall"])
            self.assertIn("pause_automation_on_completion_reason", policy)
            self.assertIn("pause_automation_on_stall_reason", policy)

    def test_scaffold_custom_approval_policy_reports_selected_operations(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()

            proc = self.run_cli(
                "scaffold",
                "--repo-root",
                str(repo_root),
                "--roadmap-slug",
                "new-roadmap",
                "--approval-mode",
                "custom",
                "--approval-operation",
                "edit_phase_owned_files=allow",
                "--approval-operation",
                "push_current_phase_branch=deny",
                "--dry-run",
                "--json",
            )
            report = json.loads(proc.stdout)

            self.assertEqual(report["approval_policy"]["approval_mode"], "custom")
            self.assertEqual(report["approval_policy"]["approved_operations"], ["edit_phase_owned_files"])

    def test_validate_reports_invalid_approval_policy_as_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_model_policy=True)
            policy_path = fixture.state_dir / "approval_policy.json"
            policy_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "approval_mode": "delegated_local",
                        "operations": {"push_current_phase_branch": True},
                        "never_auto": [],
                    }
                ),
                encoding="utf-8",
            )

            proc = self.run_cli(
                "validate",
                "--repo-root",
                str(fixture.repo_root),
                "--roadmap-slug",
                fixture.slug,
                "--automation-id",
                fixture.automation_id,
                "--json",
                env=fixture.env(),
                allowed_returncodes=(1,),
            )
            report = json.loads(proc.stdout)

            self.assertEqual(report["status"], "error")
            self.assertEqual(report["approval_policy"]["fallback_reason"], "invalid_policy")
            self.assertIn("approval_policy_operations_mismatch", {item["code"] for item in report["errors"]})

    def test_package_dry_run_reports_codex_render_plan(self):
        proc = self.run_cli(
            "package",
            "--repo-root",
            str(REPO_ROOT),
            "--adapter",
            "codex",
            "--dry-run",
            "--json",
            allowed_returncodes=(0,),
        )
        report = json.loads(proc.stdout)

        self.assertTrue(report["dry_run"])
        self.assertEqual(report["command"], "package")
        self.assertEqual(report["adapter"], "codex")
        self.assertEqual(report["would_write"], str(REPO_ROOT / "skill" / "roadmap-delivery-skill"))
        self.assertIn(str(REPO_ROOT / "core" / "references"), report["would_read"])


if __name__ == "__main__":
    unittest.main()
