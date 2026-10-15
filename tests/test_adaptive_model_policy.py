import json
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from tests.test_helper_scripts import DeliveryFixture, PLAN_SCRIPT, REPO_ROOT
except ModuleNotFoundError:  # pragma: no cover - unittest discover import style
    from test_helper_scripts import DeliveryFixture, PLAN_SCRIPT, REPO_ROOT

import sys

SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from roadmap_delivery.adaptive import classify_run_quality, resolve_adaptive_action


def adaptive_policy_text(*, enabled=True, defaults_model="gpt-5.4", defaults_reasoning="medium"):
    policy = {
        "schema_version": 1,
        "max_stalled_runs": 3,
        "notification": {"mode": "alert_file", "fallback": "alert_file"},
        "defaults": {"model": defaults_model, "reasoning_effort": defaults_reasoning},
        "phases": {
            "finalization": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
        },
        "adaptive_model_policy": {
            "enabled": enabled,
            "escalate_on": [
                "delivered_with_fixes",
                "verification_failed",
                "review_needs_fix",
                "stalled",
                "retarget_failed",
            ],
            "human_gated_qualities": [
                "blocked_human_required",
                "completion_closeout_failed",
            ],
            "deescalate_after_flawless_runs": 0,
            "escalation": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
            "caps": {
                "allowed_models": ["gpt-5.4", "gpt-5.5"],
                "max_reasoning_effort": "xhigh",
            },
        },
    }
    return json.dumps(policy, indent=2)


class AdaptiveModelPolicyTests(unittest.TestCase):
    maxDiff = None

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

    def run_validate(self, fixture, *extra_args, allowed_returncodes=(0, 1)):
        proc = subprocess.run(
            [
                "python3",
                "-m",
                "roadmap_delivery.cli",
                "validate",
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
            cwd=REPO_ROOT,
            check=False,
        )
        self.assertIn(proc.returncode, allowed_returncodes, proc.stderr or proc.stdout)
        return json.loads(proc.stdout)

    def run_inspect(self, fixture, *extra_args, allowed_returncodes=(0,)):
        proc = subprocess.run(
            [
                "python3",
                "-m",
                "roadmap_delivery.cli",
                "inspect",
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
            cwd=REPO_ROOT,
            check=False,
        )
        self.assertIn(proc.returncode, allowed_returncodes, proc.stderr or proc.stdout)
        return json.loads(proc.stdout)

    def error_codes(self, report):
        return {item["code"] for item in report.get("errors", [])}

    def test_run_quality_classification_distinguishes_fix_and_human_blockers(self):
        self.assertEqual(
            classify_run_quality(verification_status="passed", review_verdict="delivered", fix_iterations=0),
            "flawless",
        )
        self.assertEqual(
            classify_run_quality(verification_status="passed", review_verdict="delivered", fix_iterations=1),
            "delivered_with_fixes",
        )
        self.assertEqual(
            classify_run_quality(review_verdict="blocked", blocker_class="permission-gated"),
            "blocked_human_required",
        )

    def test_adaptive_action_escalates_non_flawless_within_caps(self):
        policy = json.loads(adaptive_policy_text())

        action = resolve_adaptive_action(
            policy,
            base_model="gpt-5.4",
            base_reasoning_effort="medium",
            run_quality="verification_failed",
        )

        self.assertEqual(action["action"], "escalate")
        self.assertTrue(action["target_changed"])
        self.assertEqual(action["target"], {"model": "gpt-5.5", "reasoning_effort": "xhigh"})

    def test_adaptive_action_does_not_escalate_human_gated_blocker(self):
        policy = json.loads(adaptive_policy_text())

        action = resolve_adaptive_action(
            policy,
            base_model="gpt-5.4",
            base_reasoning_effort="medium",
            run_quality="blocked_human_required",
        )

        self.assertEqual(action["action"], "none_human_gated")
        self.assertFalse(action["target_changed"])

    def test_retarget_plan_uses_adaptive_escalation_after_fix_iteration(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                write_model_policy=True,
                policy_text=adaptive_policy_text(),
                policy_model="gpt-5.4",
                policy_reasoning="medium",
                automation_model="gpt-5.4",
                automation_reasoning="medium",
            )
            roadmap_path = fixture.repo_root / "roadmaps" / fixture.roadmap_filename
            roadmap_path.write_text(
                roadmap_path.read_text(encoding="utf-8")
                + "\n## Phase 2 - Next Fixture\n\nNext fixture body.\n",
                encoding="utf-8",
            )
            state_path = fixture.state_dir / "delivery_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["review_iterations"] = 2
            state["last_completed_run_id"] = "fixture-run-1"
            state["last_review"]["run_id"] = "fixture-run-1"
            state["last_verification"]["run_id"] = "fixture-run-1"
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

            plan = self.run_plan(fixture, "--delivered-phase", "Phase 1 - Fixture")

            self.assertEqual(plan["run_quality"], "delivered_with_fixes")
            self.assertEqual(plan["adaptive_action"]["action"], "escalate")
            self.assertEqual(plan["target"]["model"], "gpt-5.5")
            self.assertEqual(plan["target"]["reasoning_effort"], "xhigh")
            self.assertEqual(plan["retarget"]["status"], "requires_approved_update")

    def test_invalid_enabled_adaptive_policy_caps_fail_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = json.loads(adaptive_policy_text())
            policy["adaptive_model_policy"].pop("caps")
            fixture = DeliveryFixture(tmp, write_model_policy=True, policy_text=json.dumps(policy))

            validate = self.run_validate(fixture)

            self.assertIn("missing_adaptive_caps", self.error_codes(validate))

    def test_unbound_recorded_target_cannot_override_current_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DeliveryFixture(
                tmp,
                write_model_policy=True,
                policy_text=adaptive_policy_text(),
                policy_model="gpt-5.4",
                policy_reasoning="medium",
                automation_model="gpt-5.5",
                automation_reasoning="xhigh",
            )
            state_path = fixture.state_dir / "delivery_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["last_adaptive_action"] = {
                "action": "escalate",
                "run_quality": "delivered_with_fixes",
                "target_phase": "Phase 1 - Fixture",
                "target": {"model": "gpt-5.5", "reasoning_effort": "xhigh"},
                "reason": "Run quality triggers adaptive escalation.",
            }
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

            report = self.run_inspect(fixture)

            self.assertEqual(report["required_model"], "gpt-5.4")
            self.assertEqual(report["required_reasoning_effort"], "medium")
            validation = self.run_validate(fixture)
            self.assertEqual(validation["model_policy"]["persisted_target_status"], "ignored_unbound")


if __name__ == "__main__":
    unittest.main()
