import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from roadmap_delivery.approval import (
    approval_decision_for_pause_context,
    approved_operations_for_mode,
    default_approval_policy,
)
from roadmap_delivery.automation import pause_saved_automation
from roadmap_delivery.progress import compute_progress_signature, record_run_result
from roadmap_delivery.validation import validate_completion_flow


class CompletionPausePolicyTests(unittest.TestCase):
    maxDiff = None

    def test_pause_saved_automation_writes_status_and_verifies_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "automations"
            config_dir = root / "fixture-delivery"
            config_dir.mkdir(parents=True)
            config = config_dir / "automation.toml"
            config.write_text(
                "\n".join(
                    [
                        'id = "fixture-delivery"',
                        'status = "ACTIVE"',
                        'model = "gpt-5.5"',
                        'reasoning_effort = "xhigh"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = pause_saved_automation(
                "fixture-delivery",
                root=root,
                timestamp="2026-05-21T12:00:00Z",
                reason="Completion safety pause.",
            )

            self.assertTrue(result["paused"])
            self.assertEqual(result["status"], "paused")
            self.assertEqual(result["previous_status"], "ACTIVE")
            self.assertEqual(result["readback_status"], "PAUSED")
            self.assertIn('status = "PAUSED"', config.read_text(encoding="utf-8"))

    def test_context_specific_conservative_completion_pause_is_allowed(self):
        conservative = {
            "operations": approved_operations_for_mode("conservative"),
            "pause_automation_on_completion": True,
            "pause_automation_on_stall": False,
        }

        completion = approval_decision_for_pause_context(conservative, "completion")
        stall = approval_decision_for_pause_context(conservative, "stall")

        self.assertEqual(completion["decision"], "allowed")
        self.assertEqual(completion["source"], "pause_automation_on_completion")
        self.assertEqual(stall["decision"], "ask")

    def test_default_conservative_policy_allows_safety_pauses_only(self):
        policy = default_approval_policy("conservative")

        completion = approval_decision_for_pause_context(policy, "completion")
        stall = approval_decision_for_pause_context(policy, "stall")

        self.assertFalse(policy["operations"]["pause_saved_automation"])
        self.assertTrue(policy["pause_automation_on_completion"])
        self.assertTrue(policy["pause_automation_on_stall"])
        self.assertEqual(completion["decision"], "allowed")
        self.assertEqual(stall["decision"], "allowed")

    def test_validation_errors_when_completed_active_despite_allowed_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            alert = repo_root / "completed.md"
            alert.write_text("completed alert\n", encoding="utf-8")
            state = {
                "status": "completed",
                "last_operator_alert": {
                    "kind": "completed",
                    "file": str(alert),
                    "notification_status": "local_alert_only",
                },
            }
            errors = []
            warnings = []

            result = validate_completion_flow(
                repo_root,
                state,
                True,
                {"last_operator_alert": state["last_operator_alert"]},
                "ACTIVE",
                default_approval_policy("delegated_local"),
                errors,
                warnings,
            )

            self.assertTrue(result["completion_pause_required"])
            self.assertIn("completed_state_pause_readback_missing", {item["code"] for item in errors})

    def test_completed_pending_pause_records_active_runner_without_claiming_paused(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            alert = repo_root / "completed.md"
            alert.write_text("completed alert\n", encoding="utf-8")
            state = {
                "status": "completed_pending_pause",
                "last_operator_alert": {
                    "kind": "completed",
                    "file": str(alert),
                    "notification_status": "local_alert_only",
                },
            }
            errors = []
            warnings = []

            result = validate_completion_flow(
                repo_root,
                state,
                True,
                {"last_operator_alert": state["last_operator_alert"]},
                "ACTIVE",
                default_approval_policy("delegated_local"),
                errors,
                warnings,
            )

            self.assertTrue(result["completion_pause_required"])
            self.assertNotIn("completed_state_pause_readback_missing", {item["code"] for item in errors})

    def test_stall_threshold_pauses_allowed_automation_and_writes_alert(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            state_dir = repo_root / "automation" / "fixture"
            state_dir.mkdir(parents=True)
            automation_root = Path(tmp) / "home" / ".codex" / "automations"
            config_dir = automation_root / "fixture-delivery"
            config_dir.mkdir(parents=True)
            (config_dir / "automation.toml").write_text(
                "\n".join(
                    [
                        'id = "fixture-delivery"',
                        'status = "ACTIVE"',
                        'model = "gpt-5.5"',
                        'reasoning_effort = "xhigh"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            state = {
                "schema_version": 1,
                "roadmap": "roadmaps/fixture.md",
                "roadmap_slug": "fixture",
                "current_phase": "Phase 1 - Fixture",
                "status": "not_started",
                "review_iterations": 0,
                "last_verification": {"status": "passed"},
                "last_review": {"verdict": "delivered"},
                "last_delivered_phase": None,
                "blocked_reason": None,
                "automation": {"id": "fixture-delivery", "status": "ACTIVE"},
                "required_model": "gpt-5.5",
                "configured_automation_model": "gpt-5.5",
                "required_reasoning_effort": "xhigh",
                "configured_automation_reasoning_effort": "xhigh",
                "run_count": 2,
                "stalled_run_count": 2,
                "max_stalled_runs": 3,
                "last_progress_signature": None,
                "last_progress_at": None,
                "last_operator_alert": None,
                "all_phases_complete": False,
                "updated_at": "2026-05-21T00:00:00Z",
            }
            state_path = state_dir / "delivery_state.json"
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            (state_dir / "delivery_log.md").write_text("# Delivery Log\n", encoding="utf-8")
            (state_dir / "approval_policy.json").write_text(
                json.dumps(default_approval_policy("delegated_local"), indent=2),
                encoding="utf-8",
            )
            signature = compute_progress_signature(repo_root, state_path, state)["progress_signature"]
            state["last_progress_signature"] = signature
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

            with patch.dict(os.environ, {"AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR": str(automation_root)}):
                result = record_run_result(
                    repo_root,
                    state_path,
                    timestamp="2026-05-21T12:05:00Z",
                    automation_id="fixture-delivery",
                )

            state_after = json.loads(state_path.read_text(encoding="utf-8"))
            alert_path = repo_root / state_after["last_operator_alert"]["file"]

            self.assertTrue(result["threshold_reached"])
            self.assertEqual(state_after["status"], "blocked")
            self.assertEqual(state_after["configured_automation_status"], "PAUSED")
            self.assertEqual(state_after["last_automation_pause"]["status"], "paused")
            self.assertEqual(state_after["last_operator_alert"]["kind"], "stalled")
            self.assertTrue(alert_path.is_file())
            self.assertIn('status = "PAUSED"', (config_dir / "automation.toml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
