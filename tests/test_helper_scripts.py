import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILL_ROOT = REPO_ROOT / "skill" / "roadmap-delivery-skill"
SKILL_ROOT = Path(
    os.environ.get(
        "ROADMAP_DELIVERY_SKILL_ROOT",
        os.environ.get("AUTONOMOUS_ROADMAP_SKILL_ROOT", DEFAULT_SKILL_ROOT),
    )
).expanduser()
INSPECT_SCRIPT = SKILL_ROOT / "scripts" / "inspect_delivery_state.py"
VALIDATE_SCRIPT = SKILL_ROOT / "scripts" / "validate_delivery_artifacts.py"
COMPUTE_SCRIPT = SKILL_ROOT / "scripts" / "compute_progress_signature.py"
WRITE_ALERT_SCRIPT = SKILL_ROOT / "scripts" / "write_operator_alert.py"
PLAN_SCRIPT = SKILL_ROOT / "scripts" / "plan_automation_retarget.py"


class DeliveryFixture:
    @staticmethod
    def build_model_policy_text(
        *,
        defaults_model="gpt-5.5",
        defaults_reasoning="xhigh",
        max_stalled_runs=2,
        notification=None,
        phases=None,
    ):
        if notification is None:
            notification = {"mode": "alert_file", "fallback": "alert_file"}
        if phases is None:
            phases = {
                "1": {"model": defaults_model, "reasoning_effort": defaults_reasoning},
                "finalization": {"model": defaults_model, "reasoning_effort": defaults_reasoning},
            }
        policy = {
            "schema_version": 1,
            "max_stalled_runs": max_stalled_runs,
            "notification": notification,
            "defaults": {"model": defaults_model, "reasoning_effort": defaults_reasoning},
            "phases": phases,
        }
        return json.dumps(policy, indent=2)

    def __init__(
        self,
        tmpdir,
        *,
        slug="eval-fixture",
        automation_status="ACTIVE",
        current_phase="Phase 1 - Fixture",
        state_status="not_started",
        roadmap_status="In Progress",
        review_verdict="delivered",
        omit_review_dir=False,
        dirty_worktree=False,
        roadmap_filename="eval_fixture_roadmap.md",
        prompt_path=None,
        prompt_state_resolved=False,
        hard_stop_guard=True,
        blocked_remediation_guard=True,
        state_layout="roadmaps",
        write_automation_config=True,
        write_model_policy=False,
        policy_text=None,
        policy_model="gpt-5.5",
        policy_reasoning="xhigh",
        automation_model="gpt-5.5",
        automation_reasoning="xhigh",
        policy_max_stalled_runs=2,
        state_run_count=0,
        state_stalled_run_count=0,
        state_max_stalled_runs=2,
        state_last_progress_signature=None,
        state_last_progress_at=None,
        state_schema_version=1,
        run_log_text=None,
        all_phases_complete=False,
        write_deep_review_prompt=False,
        final_deep_review_status=None,
        final_deep_review_waiver_reason=None,
    ):
        self.tmpdir = Path(tmpdir)
        self.repo_root = self.tmpdir / "repo"
        self.home = self.tmpdir / "home"
        self.slug = slug
        self.slug_dir = slug.replace("-", "_")
        self.automation_id = f"{slug}-delivery"
        self.roadmap_filename = roadmap_filename
        if prompt_path is None:
            prompt_path = f"roadmaps/{roadmap_filename}"
        self.repo_root.mkdir(parents=True)
        self.home.mkdir(parents=True)

        self._write_repo_files(
            current_phase=current_phase,
            state_status=state_status,
            roadmap_status=roadmap_status,
            review_verdict=review_verdict,
            omit_review_dir=omit_review_dir,
            state_layout=state_layout,
            write_model_policy=write_model_policy,
            policy_text=policy_text,
            policy_model=policy_model,
            policy_reasoning=policy_reasoning,
            policy_max_stalled_runs=policy_max_stalled_runs,
            state_run_count=state_run_count,
            state_stalled_run_count=state_stalled_run_count,
            state_max_stalled_runs=state_max_stalled_runs,
            state_last_progress_signature=state_last_progress_signature,
            state_last_progress_at=state_last_progress_at,
            state_schema_version=state_schema_version,
            run_log_text=run_log_text,
            all_phases_complete=all_phases_complete,
            write_deep_review_prompt=write_deep_review_prompt,
            final_deep_review_status=final_deep_review_status,
            final_deep_review_waiver_reason=final_deep_review_waiver_reason,
        )
        if write_automation_config:
            self._write_automation_config(
                automation_status=automation_status,
                prompt_path=prompt_path,
                prompt_state_resolved=prompt_state_resolved,
                hard_stop_guard=hard_stop_guard,
                blocked_remediation_guard=blocked_remediation_guard,
                automation_model=automation_model,
                automation_reasoning=automation_reasoning,
            )
        self._init_git()
        if dirty_worktree:
            (self.repo_root / "operator-notes.txt").write_text("unrelated local note\n", encoding="utf-8")

    def _write_repo_files(
        self,
        *,
        current_phase,
        state_status,
        roadmap_status,
        review_verdict,
        omit_review_dir,
        state_layout,
        write_model_policy,
        policy_text,
        policy_model,
        policy_reasoning,
        policy_max_stalled_runs,
        state_run_count,
        state_stalled_run_count,
        state_max_stalled_runs,
        state_last_progress_signature,
        state_last_progress_at,
        state_schema_version,
        run_log_text,
        all_phases_complete,
        write_deep_review_prompt,
        final_deep_review_status,
        final_deep_review_waiver_reason,
    ):
        roadmap_path = self.repo_root / "roadmaps" / self.roadmap_filename
        if state_layout == "root":
            state_dir = self.repo_root / "automation" / self.slug_dir
            review_prefix = f"automation/{self.slug_dir}/reviews"
        elif state_layout == "roadmaps":
            state_dir = self.repo_root / "roadmaps" / "automation" / self.slug_dir
            review_prefix = f"roadmaps/automation/{self.slug_dir}/reviews"
        else:
            raise ValueError(f"Unsupported state_layout: {state_layout}")
        self.state_dir = state_dir
        review_dir = state_dir / "reviews"
        roadmap_path.parent.mkdir(parents=True)
        state_dir.mkdir(parents=True)
        if not omit_review_dir:
            review_dir.mkdir(parents=True)

        roadmap_path.write_text(
            "\n".join(
                [
                    "# Eval Fixture Roadmap",
                    "",
                    f"Status: {roadmap_status}",
                    f"Current phase: {current_phase}",
                    "Last updated: 2026-05-21",
                    "Next action: Continue the fixture phase.",
                    "Blocked by: None",
                    "",
                    "## Phase 1 - Fixture",
                    "",
                    "Fixture body.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        state = {
            "schema_version": state_schema_version,
            "roadmap": f"roadmaps/{self.roadmap_filename}",
            "roadmap_slug": self.slug,
            "current_phase": current_phase,
            "branch": f"codex/{self.slug}-phase-1",
            "status": state_status,
            "review_iterations": 1,
            "max_review_iterations": 3,
            "last_review": {
                "file": f"{review_prefix}/{self.slug}-phase-1-review-iteration-1.md",
                "verdict": review_verdict,
            },
            "last_delivered_phase": None,
            "blocked_reason": None,
            "last_blocker_repair": None,
            "required_model": policy_model if write_model_policy else None,
            "required_reasoning_effort": policy_reasoning if write_model_policy else None,
            "configured_automation_model": policy_model if write_model_policy else None,
            "configured_automation_reasoning_effort": policy_reasoning if write_model_policy else None,
            "run_count": state_run_count,
            "stalled_run_count": state_stalled_run_count,
            "max_stalled_runs": state_max_stalled_runs,
            "last_progress_signature": state_last_progress_signature,
            "last_progress_at": state_last_progress_at,
            "last_operator_alert": None,
            "all_phases_complete": all_phases_complete,
            "updated_at": "2026-05-21T00:00:00Z",
        }
        deep_review_prompt_path = f"{review_prefix.rsplit('/reviews', 1)[0]}/deep_review_prompt.md"
        if write_deep_review_prompt:
            state["deep_review_prompt"] = deep_review_prompt_path
            state["final_deep_review_prompt_prepared"] = True
            state["final_deep_review_prompt_file"] = deep_review_prompt_path
            state["final_deep_review_status"] = final_deep_review_status or "prompt-prepared"
        elif final_deep_review_status is not None:
            state["final_deep_review_status"] = final_deep_review_status
        if final_deep_review_waiver_reason is not None:
            state["final_deep_review_waiver_reason"] = final_deep_review_waiver_reason
        if state_schema_version is None:
            state.pop("schema_version")
        (state_dir / "delivery_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
        (state_dir / "delivery_log.md").write_text("# Fixture Delivery Log\n", encoding="utf-8")
        if write_deep_review_prompt:
            (state_dir / "deep_review_prompt.md").write_text(
                "Review final roadmap completion, verification, and promotion readiness.\n",
                encoding="utf-8",
            )
        if write_model_policy:
            if policy_text is None:
                policy_text = self.build_model_policy_text(
                    defaults_model=policy_model,
                    defaults_reasoning=policy_reasoning,
                    max_stalled_runs=policy_max_stalled_runs,
                )
            (state_dir / "phase_model_policy.json").write_text(policy_text, encoding="utf-8")
        if not omit_review_dir:
            (review_dir / f"{self.slug}-phase-1-review-iteration-1.md").write_text(
                "\n".join(
                    [
                        "# Phase 1 Review - Iteration 1",
                        "",
                        "Reviewed at: 2026-05-21T00:00:00Z",
                        f"Roadmap: `roadmaps/{self.roadmap_filename}`",
                        f"Phase: {current_phase}",
                        f"Branch: `codex/{self.slug}-phase-1`",
                        "Reviewer context: fixture review.",
                        "",
                        "## Findings",
                        "",
                        "- Fixture review.",
                        "",
                        "## Verification Evidence",
                        "",
                        "- Fixture verification: passed.",
                        "",
                        "## Missing Tests Or Checks",
                        "",
                        "None.",
                        "",
                        "## Verdict",
                        "",
                        review_verdict,
                        "",
                    ]
                ),
                encoding="utf-8",
            )
        if run_log_text is not None:
            (state_dir / "automation_run_log.jsonl").write_text(run_log_text, encoding="utf-8")

    def _write_automation_config(
        self,
        *,
        automation_status,
        prompt_path,
        prompt_state_resolved,
        hard_stop_guard,
        blocked_remediation_guard,
        automation_model,
        automation_reasoning,
    ):
        automation_dir = self.home / ".codex" / "automations" / self.automation_id
        automation_dir.mkdir(parents=True)
        guard = ""
        if hard_stop_guard:
            guard = " If state is completed_pending_pause or all_phases_complete, do not start a new phase."
        blocked_guard = ""
        if blocked_remediation_guard:
            blocked_guard = " If status is blocked, enter Blocked Remediation Mode, repair local blockers before advance, and only then resume."
        prompt = f"Run the next safe step for `{prompt_path}`.{guard}{blocked_guard}"
        if prompt_state_resolved:
            prompt += " Resolve the current roadmap path from delivery_state.json; the state roadmap field is authoritative."
        (automation_dir / "automation.toml").write_text(
            "\n".join(
                [
                    'id = "' + self.automation_id + '"',
                    f'prompt = {json.dumps(prompt)}',
                    f'status = "{automation_status}"',
                    f'model = "{automation_model}"',
                    f'reasoning_effort = "{automation_reasoning}"',
                    'cwds = ["' + str(self.repo_root) + '"]',
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _init_git(self):
        subprocess.run(["git", "init", "-b", f"codex/{self.slug}-phase-1"], cwd=self.repo_root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "add", "."], cwd=self.repo_root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=automation.invalid",
                "commit",
                "-m",
                "fixture",
            ],
            cwd=self.repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def commit_all(self, message="fixture update"):
        subprocess.run(["git", "add", "."], cwd=self.repo_root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=automation.invalid",
                "commit",
                "-m",
                message,
            ],
            cwd=self.repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def env(self):
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env["PYTHONPYCACHEPREFIX"] = str(self.tmpdir / "pycache")
        return env


class HelperScriptTests(unittest.TestCase):
    maxDiff = None

    def run_json(self, script, fixture, *extra_args, allowed_returncodes=(0,)):
        proc = subprocess.run(
            [
                "python3",
                str(script),
                "--repo-root",
                str(fixture.repo_root),
                "--roadmap-slug",
                fixture.slug,
                "--automation-id",
                fixture.automation_id,
                "--json",
                *extra_args,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=fixture.env(),
            check=False,
        )
        self.assertIn(proc.returncode, allowed_returncodes, proc.stderr or proc.stdout)
        return json.loads(proc.stdout)

    def run_validate(self, fixture, *extra_args, allowed_returncodes=(0, 1)):
        return self.run_json(VALIDATE_SCRIPT, fixture, *extra_args, allowed_returncodes=allowed_returncodes)

    def run_validate_proc(self, fixture, *extra_args):
        return subprocess.run(
            [
                "python3",
                str(VALIDATE_SCRIPT),
                "--repo-root",
                str(fixture.repo_root),
                "--roadmap-slug",
                fixture.slug,
                "--automation-id",
                fixture.automation_id,
                "--json",
                *extra_args,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=fixture.env(),
            check=False,
        )

    def run_inspect(self, fixture):
        return self.run_json(INSPECT_SCRIPT, fixture)

    def run_progress(self, fixture, *extra_args, allowed_returncodes=(0,)):
        proc = subprocess.run(
            [
                "python3",
                str(COMPUTE_SCRIPT),
                "--repo-root",
                str(fixture.repo_root),
                "--roadmap-slug",
                fixture.slug,
                "--json",
                *extra_args,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=fixture.env(),
            check=False,
        )
        self.assertIn(proc.returncode, allowed_returncodes, proc.stderr or proc.stdout)
        return json.loads(proc.stdout)

    def run_alert(self, fixture, *extra_args, allowed_returncodes=(0,)):
        proc = subprocess.run(
            [
                "python3",
                str(WRITE_ALERT_SCRIPT),
                "--repo-root",
                str(fixture.repo_root),
                "--roadmap-slug",
                fixture.slug,
                "--json",
                *extra_args,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=fixture.env(),
            check=False,
        )
        self.assertIn(proc.returncode, allowed_returncodes, proc.stderr or proc.stdout)
        return json.loads(proc.stdout)

    def run_plan(self, fixture, *extra_args, allowed_returncodes=(0,)):
        proc = subprocess.run(
            [
                "python3",
                str(PLAN_SCRIPT),
                "--repo-root",
                str(fixture.repo_root),
                "--roadmap-slug",
                fixture.slug,
                "--automation-id",
                fixture.automation_id,
                "--json",
                *extra_args,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=fixture.env(),
            check=False,
        )
        self.assertIn(proc.returncode, allowed_returncodes, proc.stderr or proc.stdout)
        return json.loads(proc.stdout)

    def set_last_progress_signature_to_current(self, fixture):
        progress = self.run_progress(fixture)
        state_path = fixture.state_dir / "delivery_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["last_progress_signature"] = progress["progress_signature"]
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return progress["progress_signature"]

    def warning_codes(self, report):
        return {item["code"] for item in report.get("warnings", [])}

    def error_codes(self, report):
        return {item["code"] for item in report.get("errors", [])}

    def info_codes(self, report):
        return {item["code"] for item in report.get("info", [])}

    def test_progress_signature_first_run_records_state_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_model_policy=True)
            state_path = fixture.state_dir / "delivery_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["last_run_quality"] = "flawless"
            state["last_adaptive_action"] = {
                "action": "none",
                "run_quality": "flawless",
                "target": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
                "target_changed": False,
            }
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

            progress = self.run_progress(fixture, "--record-run", "--timestamp", "2026-05-21T12:00:00Z")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            run_log = (fixture.state_dir / "automation_run_log.jsonl").read_text(encoding="utf-8").splitlines()
            log_entry = json.loads(run_log[0])

            self.assertTrue(progress["progress_detected"])
            self.assertEqual(progress["run_count"], 1)
            self.assertEqual(progress["stalled_run_count"], 0)
            self.assertEqual(state["last_progress_signature"], progress["progress_signature"])
            self.assertEqual(state["last_progress_at"], "2026-05-21T12:00:00Z")
            self.assertEqual(len(run_log), 1)
            self.assertTrue(log_entry["progress_detected"])
            self.assertEqual(log_entry["run_quality"], "flawless")
            self.assertEqual(log_entry["adaptive_action"]["action"], "none")

    def test_progress_detected_resets_stall_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                write_model_policy=True,
                state_run_count=4,
                state_stalled_run_count=2,
                state_last_progress_signature="sha256:previous",
            )

            progress = self.run_progress(fixture, "--record-run", "--timestamp", "2026-05-21T12:01:00Z")
            state = json.loads((fixture.state_dir / "delivery_state.json").read_text(encoding="utf-8"))

            self.assertTrue(progress["progress_detected"])
            self.assertEqual(progress["run_count"], 5)
            self.assertEqual(progress["stalled_run_count"], 0)
            self.assertEqual(state["stalled_run_count"], 0)

    def test_no_progress_increments_stall_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_model_policy=True, state_run_count=2)
            self.set_last_progress_signature_to_current(fixture)

            progress = self.run_progress(fixture, "--record-run", "--timestamp", "2026-05-21T12:02:00Z")
            state = json.loads((fixture.state_dir / "delivery_state.json").read_text(encoding="utf-8"))

            self.assertFalse(progress["progress_detected"])
            self.assertEqual(progress["run_count"], 3)
            self.assertEqual(progress["stalled_run_count"], 1)
            self.assertEqual(state["status"], "not_started")

    def test_stall_threshold_marks_state_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_model_policy=True, state_run_count=5, state_stalled_run_count=1)
            self.set_last_progress_signature_to_current(fixture)

            progress = self.run_progress(fixture, "--record-run", "--timestamp", "2026-05-21T12:03:00Z")
            state = json.loads((fixture.state_dir / "delivery_state.json").read_text(encoding="utf-8"))

            self.assertFalse(progress["progress_detected"])
            self.assertTrue(progress["threshold_reached"])
            self.assertEqual(progress["stalled_run_count"], 2)
            self.assertEqual(state["status"], "blocked")
            self.assertIn("Stalled after 2 consecutive runs", state["blocked_reason"])

    def test_custom_policy_stall_threshold_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                write_model_policy=True,
                policy_max_stalled_runs=2,
                state_max_stalled_runs=3,
                state_run_count=5,
                state_stalled_run_count=1,
            )
            self.set_last_progress_signature_to_current(fixture)

            progress = self.run_progress(fixture, "--record-run", "--timestamp", "2026-05-21T12:04:00Z")
            state = json.loads((fixture.state_dir / "delivery_state.json").read_text(encoding="utf-8"))

            self.assertEqual(progress["max_stalled_runs"], 2)
            self.assertEqual(progress["max_stalled_runs_source"], "phase_model_policy")
            self.assertTrue(progress["threshold_reached"])
            self.assertEqual(state["max_stalled_runs"], 2)

    def test_corrupt_run_log_is_validation_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_model_policy=True, run_log_text="{not json\n")

            validate = self.run_validate(fixture)

            self.assertIn("invalid_run_log_jsonl", self.error_codes(validate))

    def test_operator_alert_generation_records_state_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_model_policy=True, state_status="blocked")
            state_path = fixture.state_dir / "delivery_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["last_verification"] = {
                "status": "passed",
                "checks": [
                    {
                        "command": "python3 -m unittest discover -s tests -v",
                        "status": "passed",
                    }
                ],
            }
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

            alert = self.run_alert(
                fixture,
                "--kind",
                "stalled",
                "--reason",
                "Stalled after 2 consecutive runs without durable progress.",
                "--next-action",
                "Inspect the stalled run and repair the blocker.",
                "--timestamp",
                "2026-05-21T12:05:00Z",
            )
            state = json.loads((fixture.state_dir / "delivery_state.json").read_text(encoding="utf-8"))
            alert_path = Path(alert["alert_file"])
            alert_text = alert_path.read_text(encoding="utf-8")
            delivery_log = (fixture.state_dir / "delivery_log.md").read_text(encoding="utf-8")
            validate = self.run_validate(fixture)

            self.assertTrue(alert_path.exists())
            self.assertTrue(alert["alert_file_relative"].endswith("alerts/2026-05-21T12-05-00Z-stalled.md"))
            self.assertIn("Roadmap Delivery Alert: Stalled", alert_text)
            self.assertIn("Phase: `Phase 1 - Fixture`", alert_text)
            self.assertIn("Required model: `gpt-5.5`", alert_text)
            self.assertIn("python3 -m unittest discover -s tests -v: passed", alert_text)
            self.assertIn("Next human action: Inspect the stalled run", alert_text)
            self.assertEqual(state["last_operator_alert"]["kind"], "stalled")
            self.assertEqual(state["last_operator_alert"]["notification_status"], "local_alert_only")
            self.assertIn("Operator Alert - 2026-05-21T12:05:00Z - Stalled", delivery_log)
            self.assertEqual(validate["errors"], [])

    def test_notification_failure_preserves_alert_and_records_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_model_policy=True, state_status="blocked")

            alert = self.run_alert(
                fixture,
                "--kind",
                "blocked",
                "--reason",
                "Manual permission is required before continuing.",
                "--notification-sink",
                "github_issue",
                "--notification-failure",
                "missing GitHub token",
                "--timestamp",
                "2026-05-21T12:06:00Z",
            )
            state = json.loads((fixture.state_dir / "delivery_state.json").read_text(encoding="utf-8"))
            alert_text = Path(alert["alert_file"]).read_text(encoding="utf-8")
            delivery_log = (fixture.state_dir / "delivery_log.md").read_text(encoding="utf-8")
            validate = self.run_validate(fixture)

            self.assertTrue(Path(alert["alert_file"]).exists())
            self.assertEqual(state["last_operator_alert"]["notification_status"], "failed")
            self.assertEqual(state["last_operator_alert"]["notification_failure"], "missing GitHub token")
            self.assertIn("Notification failure: missing GitHub token", alert_text)
            self.assertIn("Notification failure: missing GitHub token", delivery_log)
            self.assertEqual(validate["errors"], [])

    def test_retarget_failed_alert_generation_records_state_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_model_policy=True, state_status="blocked")

            alert = self.run_alert(
                fixture,
                "--kind",
                "retarget-failed",
                "--reason",
                "Automation readback did not match the next phase policy.",
                "--next-action",
                "Retarget the automation, read back config, and rerun validation.",
                "--timestamp",
                "2026-05-21T12:08:00Z",
            )
            state = json.loads((fixture.state_dir / "delivery_state.json").read_text(encoding="utf-8"))
            alert_path = Path(alert["alert_file"])
            alert_text = alert_path.read_text(encoding="utf-8")
            delivery_log = (fixture.state_dir / "delivery_log.md").read_text(encoding="utf-8")
            validate = self.run_validate(fixture)

            self.assertTrue(alert_path.exists())
            self.assertTrue(alert["alert_file_relative"].endswith("alerts/2026-05-21T12-08-00Z-retarget-failed.md"))
            self.assertIn("Roadmap Delivery Alert: Retarget Failed", alert_text)
            self.assertIn("Alert kind: `retarget-failed`", alert_text)
            self.assertIn("Next human action: Retarget the automation", alert_text)
            self.assertEqual(state["last_operator_alert"]["kind"], "retarget-failed")
            self.assertEqual(state["last_operator_alert"]["notification_status"], "local_alert_only")
            self.assertIn("Operator Alert - 2026-05-21T12:08:00Z - Retarget Failed", delivery_log)
            self.assertEqual(validate["errors"], [])

    def test_validate_errors_when_recorded_alert_file_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_model_policy=True)
            state_path = fixture.state_dir / "delivery_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["last_operator_alert"] = {
                "kind": "blocked",
                "file": "roadmaps/automation/eval_fixture/alerts/missing.md",
                "timestamp": "2026-05-21T12:07:00Z",
                "reason": "missing fixture alert",
                "notification_sink": "alert_file",
                "notification_status": "local_alert_only",
            }
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

            validate = self.run_validate(fixture)

            self.assertIn("missing_operator_alert_file", self.error_codes(validate))

    def test_clean_in_progress_fixture_passes_both_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp)

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertEqual(inspect["current_phase"], "Phase 1 - Fixture")
            self.assertFalse(inspect["worktree_dirty"])
            self.assertEqual(inspect["warnings"], [])
            self.assertEqual(validate["errors"], [])
            self.assertEqual(validate["warnings"], [])
            self.assertTrue(validate["blocked_remediation_guard"])

    def test_inspect_and_validate_surface_approval_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp)

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            for report in (inspect, validate):
                decisions = report["approval_policy"]["operation_decisions"]
                self.assertEqual(decisions["retarget_saved_automation"]["decision"], "ask")
                self.assertEqual(decisions["promote_to_main"]["decision"], "forbidden")
            self.assertEqual(inspect["autonomy_mode"], "conservative")
            self.assertIn("run_verification", inspect["allowed_operations"])
            self.assertEqual(inspect["pause_status"]["completion_pause_decision"]["decision"], "allowed")
            self.assertIsNone(inspect["last_run_quality"])
            self.assertIsNone(inspect["adaptive_model_decision"]["run_quality"])

    def test_validate_errors_on_delegated_state_without_policy_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp)
            state_path = fixture.state_dir / "delivery_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["approval_mode"] = "delegated_local"
            state["last_approval_policy_readback"] = {
                "status": "valid",
                "approval_mode": "delegated_local",
                "approved_operations": ["retarget_saved_automation"],
            }
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

            validate = self.run_validate(fixture)

            codes = self.error_codes(validate)
            self.assertIn("approval_policy_state_mismatch", codes)
            self.assertIn("approval_policy_readback_stale", codes)

    def test_root_automation_layout_is_supported_by_both_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, state_layout="root")

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertEqual(inspect["state_file"], str((fixture.state_dir / "delivery_state.json").resolve()))
            self.assertEqual(inspect["warnings"], [])
            self.assertEqual(validate["errors"], [])
            self.assertEqual(validate["warnings"], [])

    def test_stale_automation_prompt_path_is_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, prompt_path="roadmaps/missing_eval_fixture_roadmap.md")

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertIn("stale_automation_roadmap_path", self.warning_codes(inspect))
            self.assertIn("stale_automation_roadmap_path", self.warning_codes(validate))
            self.assertEqual(validate["errors"], [])

    def test_state_resolved_prompt_allows_lifecycle_rename_without_retarget_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                roadmap_filename="in_progress_eval_fixture_roadmap.md",
                prompt_path="roadmaps/not_started_eval_fixture_roadmap.md",
                prompt_state_resolved=True,
            )

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            inspect_codes = self.warning_codes(inspect)
            validate_codes = self.warning_codes(validate)
            self.assertNotIn("stale_automation_roadmap_path", inspect_codes)
            self.assertNotIn("automation_roadmap_path_mismatch", inspect_codes)
            self.assertNotIn("automation_prompt_current_roadmap_missing", validate_codes)
            self.assertNotIn("stale_automation_roadmap_path", validate_codes)
            self.assertNotIn("automation_roadmap_path_mismatch", validate_codes)
            self.assertTrue(inspect["state_resolved_roadmap_prompt"])
            self.assertTrue(validate["state_resolved_roadmap_prompt"])
            self.assertEqual(validate["errors"], [])

    def test_active_not_started_lifecycle_filename_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                roadmap_filename="not_started_eval_fixture_roadmap.md",
                current_phase="Phase 0 - Fixture",
                roadmap_status="Active",
            )

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertIn("roadmap_lifecycle_filename_mismatch", self.warning_codes(inspect))
            self.assertIn("roadmap_lifecycle_filename_mismatch", self.error_codes(validate))

    def test_phase_one_not_started_lifecycle_filename_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                roadmap_filename="not_started_eval_fixture_roadmap.md",
                current_phase="Phase 1 - Fixture",
                roadmap_status="Not Started",
            )

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertIn("roadmap_lifecycle_filename_mismatch", self.warning_codes(inspect))
            self.assertIn("roadmap_lifecycle_filename_mismatch", self.error_codes(validate))

    def test_phase_zero_not_started_lifecycle_filename_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                roadmap_filename="not_started_eval_fixture_roadmap.md",
                current_phase="Phase 0 - Fixture",
                roadmap_status="Not Started",
                state_status="not_started",
            )

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertNotIn("roadmap_lifecycle_filename_mismatch", self.warning_codes(inspect))
            self.assertNotIn("roadmap_lifecycle_filename_mismatch", self.error_codes(validate))

    def test_phase_zero_delivering_with_not_started_header_is_inspection_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                roadmap_filename="not_started_eval_fixture_roadmap.md",
                current_phase="Phase 0 - Fixture",
                roadmap_status="Not Started",
                state_status="delivering",
            )

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertNotIn("roadmap_lifecycle_filename_mismatch", self.warning_codes(inspect))
            self.assertNotIn("roadmap_lifecycle_filename_mismatch", self.error_codes(validate))

    def test_manual_activation_reconciliation_is_reported_for_paused_active_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                roadmap_filename="not_started_eval_fixture_roadmap.md",
                current_phase="Phase 0 - Fixture",
                roadmap_status="Not Started",
                state_status="blocked",
                review_verdict="blocked",
                write_model_policy=True,
                automation_status="ACTIVE",
            )
            state_path = fixture.state_dir / "delivery_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["blocked_reason"] = "automation-config drift: setup expected PAUSED but saved automation read back ACTIVE"
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertTrue(inspect["activation_reconciliation"]["available"])
            self.assertTrue(validate["activation_reconciliation"]["available"])
            self.assertIn("manual_activation_reconciliation_available", self.info_codes(validate))
            self.assertNotIn("blocked_state_active_without_remediation_guard", self.error_codes(validate))

    def test_missing_automation_config_is_warning_for_both_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_automation_config=False)

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertIn("missing_automation_config", self.warning_codes(inspect))
            self.assertIn("missing_automation_config", self.warning_codes(validate))
            self.assertEqual(validate["errors"], [])

    def test_completed_active_without_hard_stop_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                current_phase="Complete",
                state_status="completed",
                roadmap_status="Completed",
                hard_stop_guard=False,
            )

            validate = self.run_validate(fixture)

            self.assertIn("completed_state_active_automation", self.error_codes(validate))

    def test_completed_and_paused_with_completed_alert_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                automation_status="PAUSED",
                current_phase="Complete",
                state_status="completed",
                roadmap_status="Completed",
                roadmap_filename="delivered_eval_fixture_roadmap.md",
                write_model_policy=True,
                all_phases_complete=True,
                write_deep_review_prompt=True,
            )
            self.run_alert(
                fixture,
                "--kind",
                "completed",
                "--reason",
                "All roadmap phases are delivered and final verification passed.",
                "--next-action",
                "Preserve final evidence and keep the automation paused.",
                "--timestamp",
                "2026-05-21T12:08:00Z",
            )
            fixture.commit_all("record completed alert")

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertTrue(inspect["all_phases_complete"])
            self.assertTrue(inspect["completion_alert_present"])
            self.assertFalse(inspect["completion_pause_required"])
            self.assertFalse(validate["completion_flow"]["completion_pause_required"])
            self.assertTrue(validate["completion_flow"]["completion_alert_present"])
            self.assertEqual(inspect["final_deep_review_status"], "prompt-prepared")
            self.assertTrue(inspect["deep_review_prompt_exists"])
            self.assertEqual(validate["final_deep_review"]["status"], "prompt-prepared")
            self.assertTrue(validate["final_deep_review"]["prompt_exists"])
            self.assertEqual(validate["errors"], [])
            self.assertEqual(validate["warnings"], [])

    def test_completed_but_active_requires_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                automation_status="ACTIVE",
                current_phase="Complete",
                state_status="completed",
                roadmap_status="Completed",
                roadmap_filename="delivered_eval_fixture_roadmap.md",
                write_model_policy=True,
                all_phases_complete=True,
                write_deep_review_prompt=True,
            )
            self.run_alert(
                fixture,
                "--kind",
                "completed",
                "--reason",
                "All roadmap phases are delivered and final verification passed.",
                "--timestamp",
                "2026-05-21T12:09:00Z",
            )
            fixture.commit_all("record active completion state")

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertTrue(inspect["completion_pause_required"])
            self.assertTrue(inspect["automation_should_be_paused"])
            self.assertIn("completed_state_active_automation", self.warning_codes(inspect))
            self.assertTrue(validate["completion_flow"]["completion_pause_required"])
            self.assertIn("completed_state_active_with_hard_stop", self.warning_codes(validate))
            self.assertIn("completed_state_pause_readback_missing", self.error_codes(validate))

    def test_completed_missing_completed_alert_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                automation_status="PAUSED",
                current_phase="Complete",
                state_status="completed",
                roadmap_status="Completed",
                roadmap_filename="delivered_eval_fixture_roadmap.md",
                write_model_policy=True,
                all_phases_complete=True,
                write_deep_review_prompt=True,
            )

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertFalse(inspect["completion_alert_present"])
            self.assertIn("completed_state_missing_completed_alert", self.warning_codes(inspect))
            self.assertIn("completed_state_missing_completed_alert", self.error_codes(validate))

    def test_completed_missing_final_deep_review_prompt_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                automation_status="PAUSED",
                current_phase="Complete",
                state_status="completed",
                roadmap_status="Completed",
                roadmap_filename="delivered_eval_fixture_roadmap.md",
                write_model_policy=True,
                all_phases_complete=True,
            )
            self.run_alert(
                fixture,
                "--kind",
                "completed",
                "--reason",
                "All roadmap phases are delivered and final verification passed.",
                "--timestamp",
                "2026-05-21T12:10:00Z",
            )
            fixture.commit_all("record completed alert without final review prompt")

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertFalse(inspect["deep_review_prompt_exists"])
            self.assertIn("completed_state_missing_final_deep_review_prompt", self.warning_codes(inspect))
            self.assertIn("completed_state_missing_final_deep_review_prompt", self.error_codes(validate))

    def test_completed_final_deep_review_waiver_allows_no_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                automation_status="PAUSED",
                current_phase="Complete",
                state_status="completed",
                roadmap_status="Completed",
                roadmap_filename="delivered_eval_fixture_roadmap.md",
                write_model_policy=True,
                all_phases_complete=True,
                final_deep_review_status="waived-by-human",
                final_deep_review_waiver_reason="Human operator waived final deep review for this fixture.",
            )
            self.run_alert(
                fixture,
                "--kind",
                "completed",
                "--reason",
                "All roadmap phases are delivered and final verification passed.",
                "--timestamp",
                "2026-05-21T12:10:30Z",
            )
            fixture.commit_all("record completed alert with final review waiver")

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertTrue(inspect["final_deep_review_waived"])
            self.assertFalse(inspect["deep_review_prompt_exists"])
            self.assertNotIn("completed_state_missing_final_deep_review_prompt", self.warning_codes(inspect))
            self.assertNotIn("completed_state_missing_final_deep_review_prompt", self.error_codes(validate))
            self.assertEqual(validate["errors"], [])
            self.assertEqual(validate["warnings"], [])

    def test_invalid_final_deep_review_status_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                automation_status="PAUSED",
                current_phase="Complete",
                state_status="completed",
                roadmap_status="Completed",
                roadmap_filename="delivered_eval_fixture_roadmap.md",
                write_model_policy=True,
                all_phases_complete=True,
                write_deep_review_prompt=True,
                final_deep_review_status="done",
            )
            self.run_alert(
                fixture,
                "--kind",
                "completed",
                "--reason",
                "All roadmap phases are delivered and final verification passed.",
                "--timestamp",
                "2026-05-21T12:10:45Z",
            )
            fixture.commit_all("record completed alert with invalid final review status")

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertIn("invalid_final_deep_review_status", self.warning_codes(inspect))
            self.assertIn("invalid_final_deep_review_status", self.error_codes(validate))

    def test_completed_notification_failure_preserves_alert(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                automation_status="PAUSED",
                current_phase="Complete",
                state_status="completed",
                roadmap_status="Completed",
                roadmap_filename="delivered_eval_fixture_roadmap.md",
                write_model_policy=True,
                all_phases_complete=True,
                write_deep_review_prompt=True,
            )
            self.run_alert(
                fixture,
                "--kind",
                "completed",
                "--reason",
                "All roadmap phases are delivered and final verification passed.",
                "--notification-sink",
                "github_issue",
                "--notification-failure",
                "missing GitHub token",
                "--timestamp",
                "2026-05-21T12:10:00Z",
            )
            fixture.commit_all("record completed alert notification failure")

            validate = self.run_validate(fixture)

            alert = validate["operator_alert"]["last_operator_alert"]
            self.assertTrue(validate["completion_flow"]["completion_alert_present"])
            self.assertEqual(alert["kind"], "completed")
            self.assertEqual(alert["notification_status"], "failed")
            self.assertEqual(alert["notification_failure"], "missing GitHub token")
            self.assertEqual(validate["errors"], [])

    def test_missing_review_directory_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, omit_review_dir=True)

            validate = self.run_validate(fixture)

            self.assertIn("missing_review_dir", self.error_codes(validate))

    def test_invalid_review_verdict_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, review_verdict="approved")

            validate = self.run_validate(fixture)

            self.assertIn("invalid_review_verdict", self.error_codes(validate))

    def test_dirty_worktree_is_warning_not_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, dirty_worktree=True)

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertTrue(inspect["worktree_dirty"])
            self.assertIn("worktree_dirty", self.warning_codes(inspect))
            self.assertIn("worktree_dirty", self.warning_codes(validate))
            self.assertEqual(validate["errors"], [])

    def test_branch_mismatch_warnings_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, current_phase="Phase 2 - Fixture")

            validate = self.run_validate(fixture)

            self.assertIn("state_branch_name_mismatch", self.warning_codes(validate))
            self.assertIn("current_branch_name_mismatch", self.warning_codes(validate))
            self.assertEqual(validate["errors"], [])

    def test_missing_state_file_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp)
            (fixture.state_dir / "delivery_state.json").unlink()

            validate = self.run_validate(fixture)

            self.assertIn("missing_state_file", self.error_codes(validate))

    def test_invalid_state_json_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp)
            (fixture.state_dir / "delivery_state.json").write_text("{not valid json\n", encoding="utf-8")

            validate = self.run_validate(fixture)

            self.assertIn("invalid_state_json", self.error_codes(validate))

    def test_strict_mode_allows_named_warning_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_automation_config=False)

            strict = self.run_validate_proc(fixture, "--strict")
            allowed = self.run_validate_proc(fixture, "--strict", "--allow-warning", "missing_automation_config")

            self.assertEqual(strict.returncode, 1, strict.stdout)
            self.assertEqual(allowed.returncode, 0, allowed.stderr or allowed.stdout)

    def test_model_policy_match_reports_model_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_model_policy=True)

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertEqual(validate["errors"], [])
            self.assertEqual(validate["warnings"], [])
            self.assertEqual(validate["model_policy"]["required_model"], "gpt-5.5")
            self.assertEqual(validate["model_policy"]["configured_model"], "gpt-5.5")
            self.assertFalse(validate["model_policy"]["model_mismatch"])
            self.assertEqual(inspect["required_model"], "gpt-5.5")
            self.assertEqual(inspect["configured_automation_model"], "gpt-5.5")
            self.assertFalse(inspect["model_mismatch"])
            self.assertEqual(inspect["stalled_run_count"], 0)

    def test_model_policy_phase_override_controls_required_values(self):
        policy_text = DeliveryFixture.build_model_policy_text(
            defaults_model="gpt-5.4",
            defaults_reasoning="medium",
            phases={
                "2": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
                "finalization": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                current_phase="Phase 2 - Fixture",
                write_model_policy=True,
                policy_text=policy_text,
                automation_model="gpt-5.5",
                automation_reasoning="xhigh",
            )

            validate = self.run_validate(fixture)

            self.assertEqual(validate["model_policy"]["required_model"], "gpt-5.5")
            self.assertEqual(validate["model_policy"]["required_reasoning_effort"], "xhigh")
            self.assertFalse(validate["model_policy"]["model_mismatch"])
            self.assertNotIn("automation_model_mismatch", self.error_codes(validate))
            self.assertNotIn("automation_reasoning_mismatch", self.error_codes(validate))

    def test_higher_configured_reasoning_satisfies_required_floor(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                write_model_policy=True,
                policy_model="gpt-5.5",
                policy_reasoning="high",
                automation_model="gpt-5.5",
                automation_reasoning="xhigh",
            )

            inspect = self.run_inspect(fixture)
            validate = self.run_validate(fixture)

            self.assertEqual(validate["errors"], [])
            self.assertEqual(validate["warnings"], [])
            self.assertFalse(validate["model_policy"]["reasoning_mismatch"])
            self.assertTrue(validate["model_policy"]["reasoning_satisfied"])
            self.assertTrue(validate["model_policy"]["reasoning_over_required"])
            self.assertNotIn("automation_reasoning_mismatch", self.error_codes(validate))
            self.assertFalse(inspect["reasoning_mismatch"])
            self.assertTrue(inspect["reasoning_satisfied"])
            self.assertTrue(inspect["reasoning_over_required"])

    def test_lower_configured_reasoning_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                write_model_policy=True,
                policy_model="gpt-5.5",
                policy_reasoning="xhigh",
                automation_model="gpt-5.5",
                automation_reasoning="high",
            )

            validate = self.run_validate(fixture)

            self.assertIn("automation_reasoning_mismatch", self.error_codes(validate))
            self.assertTrue(validate["model_policy"]["reasoning_mismatch"])
            self.assertFalse(validate["model_policy"]["reasoning_satisfied"])

    def test_model_policy_finalization_override_controls_required_values(self):
        policy_text = DeliveryFixture.build_model_policy_text(
            defaults_model="gpt-5.4",
            defaults_reasoning="medium",
            phases={
                "1": {"model": "gpt-5.4", "reasoning_effort": "medium"},
                "finalization": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                current_phase="finalization",
                write_model_policy=True,
                policy_text=policy_text,
                automation_model="gpt-5.5",
                automation_reasoning="xhigh",
            )

            validate = self.run_validate(fixture)

            self.assertEqual(validate["model_policy"]["required_model"], "gpt-5.5")
            self.assertEqual(validate["model_policy"]["required_reasoning_effort"], "xhigh")
            self.assertFalse(validate["model_policy"]["reasoning_mismatch"])

    def test_model_policy_mismatch_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                write_model_policy=True,
                policy_model="gpt-5.5",
                automation_model="gpt-5.4",
            )

            validate = self.run_validate(fixture)

            self.assertIn("automation_model_mismatch", self.error_codes(validate))
            self.assertTrue(validate["model_policy"]["model_mismatch"])

    def test_model_policy_unknown_config_is_error_when_state_cannot_prove_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_model_policy=True, write_automation_config=False)
            state_path = fixture.state_dir / "delivery_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["configured_automation_model"] = None
            state["configured_automation_reasoning_effort"] = None
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

            validate = self.run_validate(fixture)

            codes = self.error_codes(validate)
            self.assertIn("automation_model_unknown", codes)
            self.assertIn("automation_reasoning_unknown", codes)
            self.assertIn("missing_automation_config", self.warning_codes(validate))
            self.assertTrue(validate["model_policy"]["model_unknown"])
            self.assertTrue(validate["model_policy"]["reasoning_unknown"])

    def test_invalid_model_policy_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                write_model_policy=True,
                policy_text='{"schema_version": 1, "max_stalled_runs": 0, "notification": {"mode": "mystery"}, "defaults": {"model": "gpt-5.5", "reasoning_effort": "giant"}, "phases": {}}',
            )

            validate = self.run_validate(fixture)

            codes = self.error_codes(validate)
            self.assertIn("invalid_max_stalled_runs", codes)
            self.assertIn("invalid_notification_mode", codes)
            self.assertIn("invalid_default_reasoning_effort", codes)

    def test_invalid_phase_model_policy_entries_are_errors(self):
        policy_text = DeliveryFixture.build_model_policy_text(
            phases={
                "1": {"model": "gpt-5.5", "reasoning_effort": "warp"},
                "2": "not an object",
                "finalization": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_model_policy=True, policy_text=policy_text)

            validate = self.run_validate(fixture)

            codes = self.error_codes(validate)
            self.assertIn("invalid_phase_reasoning_effort", codes)
            self.assertIn("invalid_phase_policy_entry", codes)

    def test_retarget_plan_uses_next_phase_policy_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(tmp, write_model_policy=True)
            roadmap_path = fixture.repo_root / "roadmaps" / fixture.roadmap_filename
            roadmap_path.write_text(
                roadmap_path.read_text(encoding="utf-8")
                + "\n## Phase 2 - Next Fixture\n\nNext fixture body.\n",
                encoding="utf-8",
            )
            policy_text = DeliveryFixture.build_model_policy_text(
                defaults_model="gpt-5.4",
                defaults_reasoning="medium",
                phases={
                    "2": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
                    "finalization": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
                },
            )
            (fixture.state_dir / "phase_model_policy.json").write_text(policy_text, encoding="utf-8")

            plan = self.run_plan(fixture, "--delivered-phase", "Phase 1 - Fixture")

            self.assertEqual(plan["next_phase"], "Phase 2 - Next Fixture")
            self.assertEqual(plan["target"]["source"], "phases.2")
            self.assertEqual(plan["target"]["model"], "gpt-5.5")
            self.assertEqual(plan["target"]["reasoning_effort"], "xhigh")
            self.assertEqual(plan["retarget"]["status"], "not_needed")

    def test_retarget_plan_does_not_require_reasoning_downgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                write_model_policy=True,
                automation_model="gpt-5.5",
                automation_reasoning="xhigh",
            )
            roadmap_path = fixture.repo_root / "roadmaps" / fixture.roadmap_filename
            roadmap_path.write_text(
                roadmap_path.read_text(encoding="utf-8")
                + "\n## Phase 2 - Next Fixture\n\nNext fixture body.\n",
                encoding="utf-8",
            )
            policy_text = DeliveryFixture.build_model_policy_text(
                defaults_model="gpt-5.5",
                defaults_reasoning="xhigh",
                phases={
                    "2": {"model": "gpt-5.5", "reasoning_effort": "high"},
                    "finalization": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
                },
            )
            (fixture.state_dir / "phase_model_policy.json").write_text(policy_text, encoding="utf-8")

            plan = self.run_plan(fixture, "--delivered-phase", "Phase 1 - Fixture")

            self.assertEqual(plan["next_phase"], "Phase 2 - Next Fixture")
            self.assertEqual(plan["target"]["reasoning_effort"], "high")
            self.assertEqual(plan["automation"]["configured_reasoning_effort"], "xhigh")
            self.assertTrue(plan["automation"]["reasoning_satisfied"])
            self.assertTrue(plan["automation"]["reasoning_over_required"])
            self.assertEqual(plan["retarget"]["status"], "not_needed")
            self.assertFalse(plan["retarget"]["update_required"])
            self.assertFalse(plan["retarget"]["reasoning_update_required"])
            self.assertTrue(plan["retarget"]["reasoning_downgrade_not_required"])

    def test_retarget_plan_mismatch_requires_update_and_can_report_failure_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                write_model_policy=True,
                automation_model="gpt-5.4",
                automation_reasoning="medium",
            )
            roadmap_path = fixture.repo_root / "roadmaps" / fixture.roadmap_filename
            roadmap_path.write_text(
                roadmap_path.read_text(encoding="utf-8")
                + "\n## Phase 2 - Next Fixture\n\nNext fixture body.\n",
                encoding="utf-8",
            )
            policy_text = DeliveryFixture.build_model_policy_text(
                defaults_model="gpt-5.4",
                defaults_reasoning="medium",
                phases={
                    "2": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
                    "finalization": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
                },
            )
            (fixture.state_dir / "phase_model_policy.json").write_text(policy_text, encoding="utf-8")

            plan = self.run_plan(fixture, "--delivered-phase", "Phase 1 - Fixture")
            failed = self.run_plan(
                fixture,
                "--delivered-phase",
                "Phase 1 - Fixture",
                "--simulate-update-failure",
                "readback still reported gpt-5.4/medium",
            )

            self.assertEqual(plan["retarget"]["status"], "requires_approved_update")
            self.assertTrue(plan["retarget"]["update_required"])
            self.assertEqual(plan["automation"]["configured_model"], "gpt-5.4")
            self.assertEqual(plan["target"]["model"], "gpt-5.5")
            self.assertEqual(failed["retarget"]["status"], "failed")
            self.assertTrue(failed["retarget"]["simulated_failure"])
            self.assertEqual(failed["failure_path"]["state_status"], "blocked")
            self.assertEqual(failed["failure_path"]["alert_kind"], "retarget-failed")
            self.assertTrue(failed["failure_path"]["stop_before_next_phase"])

    def test_retarget_plan_honors_preapproved_automation_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                write_model_policy=True,
                automation_model="gpt-5.4",
                automation_reasoning="medium",
            )
            roadmap_path = fixture.repo_root / "roadmaps" / fixture.roadmap_filename
            roadmap_path.write_text(
                roadmap_path.read_text(encoding="utf-8")
                + "\n## Phase 2 - Next Fixture\n\nNext fixture body.\n",
                encoding="utf-8",
            )
            policy_text = DeliveryFixture.build_model_policy_text(
                defaults_model="gpt-5.4",
                defaults_reasoning="medium",
                phases={
                    "2": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
                    "finalization": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
                },
            )
            (fixture.state_dir / "phase_model_policy.json").write_text(policy_text, encoding="utf-8")
            (fixture.state_dir / "approval_policy.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "approval_mode": "delegated_local",
                        "operations": {},
                        "never_auto": [],
                    }
                ),
                encoding="utf-8",
            )

            plan = self.run_plan(fixture, "--delivered-phase", "Phase 1 - Fixture")

            self.assertEqual(plan["approval_policy"]["approval_mode"], "delegated_local")
            self.assertEqual(plan["retarget"]["status"], "approved_update_available")
            self.assertFalse(plan["retarget"]["approval_required"])
            self.assertEqual(plan["retarget"]["approval_decision"]["decision"], "allowed")

    def test_model_policy_replay_prompts_cover_required_scenarios(self):
        prompt_text = (REPO_ROOT / "evals" / "model-policy-prompts.md").read_text(encoding="utf-8")

        for marker in (
            "Wrong Model At Start",
            "Retarget Next Phase",
            "Three Stalled Runs",
            "Custom Stalled Run Threshold",
            "Delivered Roadmap Completion Alert",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, prompt_text)

    def test_blocked_active_without_remediation_guard_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                state_status="blocked",
                review_verdict="blocked",
                blocked_remediation_guard=False,
            )

            validate = self.run_validate(fixture)

            self.assertIn("blocked_state_active_without_remediation_guard", self.error_codes(validate))
            self.assertIn("automation_prompt_missing_blocked_remediation_guard", self.warning_codes(validate))


if __name__ == "__main__":
    unittest.main()
