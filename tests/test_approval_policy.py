import json
import tempfile
import unittest
from pathlib import Path

from roadmap_delivery.approval import (
    approval_decision_for_operation,
    approval_decision_for_pause_context,
    approved_operation_names,
    approved_operations_for_mode,
    default_approval_policy,
    read_approval_policy,
    validate_approval_policy,
)
from roadmap_delivery.validation import validate_json_schema


REPO_ROOT = Path(__file__).resolve().parents[1]


class ApprovalPolicyTests(unittest.TestCase):
    maxDiff = None

    def test_standard_modes_expose_expected_operations(self):
        conservative = approved_operations_for_mode("conservative")
        delegated_local = approved_operations_for_mode("delegated_local")
        delegated_delivery = approved_operations_for_mode("delegated_delivery")

        self.assertTrue(conservative["edit_phase_owned_files"])
        self.assertTrue(conservative["run_verification"])
        self.assertFalse(conservative["retarget_saved_automation"])
        self.assertTrue(delegated_local["retarget_saved_automation"])
        self.assertTrue(delegated_local["pause_saved_automation"])
        self.assertFalse(delegated_local["push_current_phase_branch"])
        self.assertTrue(delegated_delivery["push_current_phase_branch"])
        self.assertFalse(default_approval_policy("conservative")["operations"]["pause_saved_automation"])
        self.assertTrue(default_approval_policy("conservative")["pause_automation_on_completion"])
        self.assertTrue(default_approval_policy("conservative")["pause_automation_on_stall"])
        self.assertTrue(default_approval_policy("delegated_local")["pause_automation_on_completion"])
        opt_out = default_approval_policy("conservative", pause_on_completion=False, pause_on_stall=False)
        self.assertFalse(opt_out["pause_automation_on_completion"])
        self.assertIn("pause_automation_on_completion_reason", opt_out)
        self.assertIn("pause_automation_on_stall_reason", opt_out)

    def test_operation_resolver_distinguishes_allowed_ask_and_forbidden(self):
        conservative = approved_operations_for_mode("conservative")
        delegated_local = approved_operations_for_mode("delegated_local")

        self.assertEqual(
            approval_decision_for_operation(delegated_local, "retarget_saved_automation")["decision"],
            "allowed",
        )
        self.assertEqual(
            approval_decision_for_operation(conservative, "retarget_saved_automation")["decision"],
            "ask",
        )
        self.assertEqual(
            approval_decision_for_pause_context(
                {"operations": conservative, "pause_automation_on_completion": True},
                "completion",
            )["decision"],
            "allowed",
        )
        self.assertEqual(
            approval_decision_for_pause_context(
                {"operations": conservative, "pause_automation_on_stall": False},
                "stall",
            )["decision"],
            "ask",
        )
        destructive = approval_decision_for_operation(delegated_local, "destructive_git")
        self.assertEqual(destructive["decision"], "forbidden")
        self.assertIn("never automatic", destructive["reason"])

    def test_missing_policy_uses_conservative_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            state_dir = repo_root / "automation" / "fixture"
            state_dir.mkdir(parents=True)
            state_file = state_dir / "delivery_state.json"
            state = {"roadmap_slug": "fixture"}
            state_file.write_text(json.dumps(state), encoding="utf-8")

            report = read_approval_policy(repo_root, state_file, state)

        self.assertFalse(report["present"])
        self.assertEqual(report["approval_mode"], "conservative")
        self.assertEqual(report["fallback_reason"], "missing_policy")
        self.assertIn("edit_phase_owned_files", report["approved_operations"])
        self.assertNotIn("push_current_phase_branch", report["approved_operations"])
        self.assertEqual(report["operation_decisions"]["retarget_saved_automation"]["decision"], "ask")
        self.assertEqual(report["operation_decisions"]["promote_to_main"]["decision"], "forbidden")
        self.assertEqual(report["errors"], [])

    def test_existing_policy_without_pause_flags_inherits_safe_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            state_dir = repo_root / "automation" / "fixture"
            state_dir.mkdir(parents=True)
            state_file = state_dir / "delivery_state.json"
            state = {"approval_policy_path": "automation/fixture/approval_policy.json"}
            state_file.write_text(json.dumps(state), encoding="utf-8")
            policy = default_approval_policy("conservative")
            policy.pop("pause_automation_on_completion")
            policy.pop("pause_automation_on_stall")
            (state_dir / "approval_policy.json").write_text(json.dumps(policy), encoding="utf-8")

            report = read_approval_policy(repo_root, state_file, state)

        self.assertTrue(report["present"])
        self.assertTrue(report["pause_automation_on_completion"])
        self.assertTrue(report["pause_automation_on_stall"])
        self.assertEqual(approval_decision_for_pause_context(report, "completion")["decision"], "allowed")
        self.assertEqual(approval_decision_for_pause_context(report, "stall")["decision"], "allowed")

    def test_custom_policy_missing_operations_default_to_denied(self):
        policy = default_approval_policy("custom", {"push_current_phase_branch": True})

        self.assertEqual(validate_approval_policy(policy), [])
        self.assertEqual(approved_operation_names(policy["operations"]), ["push_current_phase_branch"])
        self.assertFalse(policy["operations"]["edit_phase_owned_files"])

    def test_invalid_policy_reports_errors_and_conservative_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            state_dir = repo_root / "automation" / "fixture"
            state_dir.mkdir(parents=True)
            state_file = state_dir / "delivery_state.json"
            state = {"approval_policy_path": "automation/fixture/approval_policy.json"}
            state_file.write_text(json.dumps(state), encoding="utf-8")
            (state_dir / "approval_policy.json").write_text(
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

            report = read_approval_policy(repo_root, state_file, state)

        self.assertTrue(report["present"])
        self.assertEqual(report["approval_mode"], "conservative")
        self.assertEqual(report["fallback_reason"], "invalid_policy")
        self.assertIn("approval_policy_operations_mismatch", {item["code"] for item in report["errors"]})

    def test_schema_represents_custom_operation_map(self):
        schema = json.loads((REPO_ROOT / "schemas" / "approval_policy.schema.json").read_text(encoding="utf-8"))
        custom_policy = default_approval_policy(
            "custom",
            {
                "edit_phase_owned_files": True,
                "push_current_phase_branch": False,
            },
        )

        errors = validate_json_schema(custom_policy, schema)

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
