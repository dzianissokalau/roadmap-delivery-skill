import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from roadmap_delivery.approval import (
    APPROVAL_MODES, approval_decision_for_pause_context,
    default_approval_policy, execution_policy_report, read_approval_policy,
)
from roadmap_delivery.control import decide_control, RESULT_EXIT_CODES
from roadmap_delivery.reports import generated_control_bridge


ROOT = Path(__file__).resolve().parents[1]


def runner(status="ACTIVE"):
    identity = {"id": "fixture", "cwd": "/fixture", "project_id": "project", "execution_environment": "local"}
    return {
        "kind": "scheduled", "expected": identity,
        "observed": {**identity, "status": status, "model": "fixture-model", "reasoning_effort": "xhigh",
                     "prompt_guards": {"state_first": True, "terminal": True, "blocked_remediation": True}},
        "capabilities": {"status_update": True, "readback": True},
    }


def final_evidence():
    return {"final_verification_passed": True, "delivered_review": True, "final_deep_review_prompt_present": True}


def phase_state(**changes):
    return {"status": "not_started", "current_phase": "Phase 1 - Fixture",
            "required_model": "fixture-model", "required_reasoning_effort": "high",
            "stalled_run_count": 0, "max_stalled_runs": 2, **changes}


class RuntimeControlTests(unittest.TestCase):
    def test_pause_cross_product_modes_flags_and_broad_permission(self):
        # Effective operation reports can vary independently of mode; raw standard
        # policies with mismatched maps must still be rejected for execution.
        for mode in APPROVAL_MODES:
            for broad in (False, True):
                for flag in (None, False, True):
                    for context in ("completion", "stall"):
                        with self.subTest(mode=mode, broad=broad, flag=flag, context=context):
                            report = {"approval_mode": mode, "operations": {"pause_saved_automation": broad}}
                            if flag is not None:
                                report[f"pause_automation_on_{context}"] = flag
                            decision = approval_decision_for_pause_context(report, context)
                            self.assertEqual(decision["decision"], "disabled" if flag is False else "allowed")
                            if flag is False:
                                self.assertEqual(decision["reason_code"], "context_pause_disabled")

    def test_real_valid_modes_preserve_opt_outs_through_normalization(self):
        for mode in APPROVAL_MODES:
            for flag in (None, False, True):
                policy = default_approval_policy(mode, {"pause_saved_automation": True}, pause_on_completion=flag, pause_on_stall=flag)
                for context in ("completion", "stall"):
                    report = execution_policy_report(policy)
                    self.assertTrue(report["execution_valid"])
                    self.assertEqual(approval_decision_for_pause_context(report, context)["decision"], "disabled" if flag is False else "allowed")

    def test_terminal_before_model_and_activation(self):
        state = phase_state(status="completed", configured_automation_status="PAUSED", required_model="wrong")
        plan = decide_control(state, evidence=final_evidence(), runner=runner())
        self.assertEqual(plan["stage"], "terminal_reconciliation")
        self.assertEqual(plan["action"], "pause_status_only")
        self.assertFalse(plan["extract_phase"])
        self.assertFalse(plan["completion_claim"])
        self.assertTrue(plan["required_effects"][1]["readback_required"])

    def test_all_terminal_markers_hard_stop(self):
        for changes in ({"status": "completed"}, {"status": "completed_pending_pause"}, {"all_phases_complete": True}):
            plan = decide_control(phase_state(**changes), runner=runner())
            self.assertEqual(plan["stage"], "terminal_reconciliation")
            self.assertFalse(plan["extract_phase"])

    def test_missing_final_evidence_still_allows_pause_without_completion_claim(self):
        plan = decide_control(phase_state(all_phases_complete=True), runner=runner())
        self.assertEqual(plan["action"], "reconcile_completion")
        self.assertFalse(plan["completion_claim"])
        self.assertEqual(plan["required_effects"][1]["operation"], "pause_status_only")

    def test_disabled_unsupported_invalid_and_pending_are_distinct(self):
        state = phase_state(status="completed")
        disabled = decide_control(state, default_approval_policy("delegated_local", pause_on_completion=False), runner=runner())
        unsupported_runner = runner(); unsupported_runner["capabilities"] = {}
        unsupported = decide_control(state, runner=unsupported_runner)
        invalid = decide_control(state, {"approval_mode": "custom"}, runner=runner())
        pending = decide_control(state, evidence={"pause_request_accepted": True}, runner=runner())
        for plan, result in ((disabled, "disabled"), (unsupported, "unsupported"), (invalid, "invalid_input"), (pending, "pending")):
            self.assertEqual(plan["result"], result)
            self.assertFalse(any(e["operation"] == "pause_status_only" for e in plan["required_effects"]))

    def test_confirmed_pause_and_manual_finalization(self):
        state = phase_state(status="completed_pending_pause")
        paused = decide_control(state, evidence=final_evidence(), runner=runner("PAUSED"))
        self.assertEqual(paused["action"], "record_receipt")
        self.assertTrue(paused["completion_claim"])
        self.assertEqual(paused["proposed_state_changes"]["status"], "completed")
        self.assertFalse(any(e["operation"] == "pause_status_only" for e in paused["required_effects"]))
        manual = decide_control(state, evidence=final_evidence(), runner={"kind": "manual"})
        self.assertEqual(manual["result"], "not_applicable")
        self.assertTrue(manual["completion_claim"])

    def test_separately_scoped_manual_pause_does_not_rewrite_opt_out(self):
        policy = default_approval_policy("delegated_local", pause_on_completion=False)
        authority = {"authorized": True, "operation": "pause_saved_automation", "runner_id": "fixture", "source": "operator-request-7"}
        for value in (policy, {"broken": True}):
            plan = decide_control(phase_state(status="completed"), value, {"manual_pause_authority": authority}, runner())
            self.assertEqual(plan["required_effects"][-1]["context"], "manual")
            self.assertEqual(plan["authority"]["source"], "operator-request-7")
        self.assertFalse(policy["pause_automation_on_completion"])
        wrong = {**authority, "runner_id": "other"}
        plan = decide_control(phase_state(status="completed"), policy, {"manual_pause_authority": wrong}, runner())
        self.assertEqual(plan["result"], "disabled")

    def test_activation_requires_identity_configuration_and_guards(self):
        state = phase_state(configured_automation_status="PAUSED")
        good = decide_control(state, runner=runner())
        self.assertEqual(good["action"], "reconcile_activation")
        self.assertNotIn("stalled_run_count", good["proposed_state_changes"])
        for key in ("id", "cwd", "project_id", "execution_environment", "model", "reasoning_effort", "prompt_guards"):
            observed = runner(); observed["observed"][key] = "wrong"
            with self.subTest(key=key):
                self.assertEqual(decide_control(state, runner=observed)["action"], "record_mismatch")
        completed = decide_control({**state, "all_phases_complete": True}, runner=runner())
        self.assertEqual(completed["stage"], "terminal_reconciliation")

    def test_stall_precedes_remediation_and_preserves_original_blocker(self):
        state = phase_state(status="blocked", blocked_reason="missing input", stalled_run_count=2)
        plan = decide_control(state, runner=runner())
        self.assertEqual(plan["action"], "alert_and_pause")
        self.assertNotIn("blocked_reason", plan["proposed_state_changes"])
        resumed = decide_control(state, runner=runner(), event="operator_resume")
        self.assertEqual(resumed["action"], "alert_and_pause")
        self.assertNotIn("stalled_run_count", resumed["proposed_state_changes"])

    def test_explicit_budget_is_separate_from_progress(self):
        state = phase_state(status="blocked", stalled_run_count=2, run_count=2)
        plan = decide_control(state, evidence={"fresh_budget_authority": {"authorized": True, "source": "operator-budget"}}, runner=runner(), event="operator_resume")
        self.assertEqual(plan["action"], "archive_epoch_and_activate")
        self.assertEqual(plan["proposed_state_changes"]["stalled_run_count"], 0)
        self.assertNotIn("run_count", plan["proposed_state_changes"])

    def test_blocker_clears_only_with_verified_original_cause(self):
        state = phase_state(status="blocked", blocked_reason="input absent", stalled_run_count=1)
        evidence = {"blocker_class": "local-repairable", "repair_verified": True}
        self.assertEqual(decide_control(state, evidence=evidence)["action"], "repair_blocker")
        evidence.update(repaired_blocker="input absent", repair_verification="check-input.txt")
        plan = decide_control(state, evidence=evidence)
        self.assertEqual(plan["action"], "clear_verified_cause")
        self.assertIsNone(plan["proposed_state_changes"]["blocked_reason"])
        self.assertNotIn("stalled_run_count", plan["proposed_state_changes"])
        evidence["repaired_blocker"] = "other"
        self.assertEqual(decide_control(state, evidence=evidence)["action"], "repair_blocker")

    def test_phase_gate_observed_model_reasoning_and_edit_authority(self):
        state = phase_state(); evidence = {"prerequisites_passed": True}
        good = decide_control(state, evidence=evidence, runner=runner())
        self.assertTrue(good["extract_phase"])
        for key, value in (("model", "other"), ("reasoning_effort", "low")):
            bad = runner(); bad["observed"][key] = value
            self.assertEqual(decide_control(state, evidence=evidence, runner=bad)["reason_code"], "phase_model_mismatch")
        denied = default_approval_policy("custom", {"edit_phase_owned_files": False})
        self.assertEqual(decide_control(state, denied, evidence, runner())["result"], "permission_required")

    def test_fresh_current_phase_review_required_before_advancement(self):
        state = phase_state()
        evidence = {"prerequisites_passed": True, "review_verdict": "delivered", "acceptance_passed": True,
                    "verification_passed": True, "review_fresh": True, "review_file": "review.md",
                    "review_phase": state["current_phase"], "next_numbered_phase": "Phase 2 - Next"}
        good = decide_control(state, evidence=evidence, runner=runner(), event="advance_phase")
        self.assertEqual(good["action"], "plan_next_and_stop")
        self.assertFalse(good["extract_phase"])
        for key in ("review_fresh", "acceptance_passed", "verification_passed", "review_file", "review_phase"):
            bad = {**evidence, key: False}
            self.assertEqual(decide_control(state, evidence=bad, runner=runner(), event="advance_phase")["reason_code"], "delivery_gate_incomplete")
        final = decide_control(state, evidence={**evidence, "next_numbered_phase": None}, runner=runner(), event="advance_phase")
        self.assertEqual(final["action"], "prepare_finalization")
        self.assertNotIn("all_phases_complete", final["proposed_state_changes"])

    def test_fix_iteration_limit(self):
        evidence = {"prerequisites_passed": True, "review_verdict": "needs-fix"}
        self.assertEqual(decide_control(phase_state(review_iterations=1), evidence=evidence, runner=runner(), event="phase_review")["action"], "fix_current_phase")
        self.assertEqual(decide_control(phase_state(review_iterations=3), evidence=evidence, runner=runner(), event="phase_review")["reason_code"], "review_iterations_exhausted")

    def test_purity_determinism_and_input_isolation(self):
        args = (phase_state(status="completed"), default_approval_policy(), final_evidence(), runner())
        before = copy.deepcopy(args)
        with patch("builtins.open", side_effect=AssertionError("filesystem effect")), patch("pathlib.Path.read_text", side_effect=AssertionError("filesystem effect")), patch("subprocess.run", side_effect=AssertionError("process effect")):
            first = decide_control(*args); second = decide_control(*args)
        self.assertEqual(first, second)
        first["authority"]["source"] = "changed"
        self.assertEqual(args, before)
        self.assertEqual(second["exit_code"], RESULT_EXIT_CODES[second["result"]])

    def test_invalid_policy_fallback_never_grants_execution_authority(self):
        invalid = [[], {}, {"schema_version": True}, {"broken": True}]
        base = default_approval_policy()
        invalid.extend([{**base, "pause_automation_on_completion": "false"}, {**base, "operations": {"pause_saved_automation": "true"}}])
        for policy in invalid:
            report = execution_policy_report(policy)
            self.assertFalse(report["execution_valid"])
            self.assertEqual(report["approved_operations"], [])
            self.assertTrue(all(item["decision"] == "forbidden" for item in report["operation_decisions"].values()))
            self.assertEqual(decide_control(phase_state(), policy, runner=runner())["reason_code"], "invalid_policy")
            self.assertEqual(decide_control(phase_state(status="completed"), report, runner=runner())["action"], "record_policy_blocker")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp); state_file = path / "delivery_state.json"
            (path / "approval_policy.json").write_text("null")
            self.assertFalse(read_approval_policy(path, state_file, {})["execution_valid"])

    def test_generated_bridges_exact_and_behaviorally_equivalent(self):
        bridge = generated_control_bridge(ROOT)
        for name in ("plan_phase_prerequisites.py", "plan_automation_retarget.py"):
            path = ROOT / "adapters/codex/templates/scripts" / name
            text = path.read_text()
            self.assertIn(bridge, text)
            spec = importlib.util.spec_from_file_location(name[:-3], path)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            for mode in APPROVAL_MODES:
                for flag in (None, False, True):
                    policy = default_approval_policy(mode, {"pause_saved_automation": True}, pause_on_completion=flag, pause_on_stall=flag)
                    for status in ("completed", "blocked", "not_started"):
                        state = phase_state(status=status, stalled_run_count=2 if status == "blocked" else 0)
                        args = (state, policy, final_evidence(), runner())
                        self.assertEqual(module.decide_control(*args), decide_control(*args))
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); state_file = root / "delivery_state.json"
                for value in (None, {}, default_approval_policy("delegated_local", pause_on_completion=False), {"schema_version": 1, "approval_mode": "custom", "operations": {"unknown": True}, "never_auto": []}):
                    p = root / "approval_policy.json"
                    if value is None:
                        if p.exists(): p.unlink()
                    else:
                        p.write_text(json.dumps(value))
                    self.assertEqual(module.read_approval_policy(root, state_file, {}), read_approval_policy(root, state_file, {}))

    def test_run_accounting_requires_validated_active_run_evidence(self):
        for event in ("record_outcome", "recover_run"):
            plan = decide_control(phase_state(), event=event)
            self.assertEqual(plan["reason_code"], "invalid_run_evidence")
            self.assertNotIn("run_count", plan["proposed_state_changes"])

    def test_already_paused_needs_readback_but_no_update_capability(self):
        observed = runner("PAUSED"); observed["capabilities"] = {"readback": True}
        plan = decide_control(phase_state(status="completed"), evidence=final_evidence(), runner=observed)
        self.assertEqual(plan["action"], "record_receipt")
        self.assertTrue(plan["completion_claim"])

    def test_malformed_inputs_return_invalid_without_coercion(self):
        for state, evidence, snapshot in (([], None, None), (phase_state(), [], None), (phase_state(), None, []),
                (phase_state(), None, {"expected": "bad"}), (phase_state(automation="bad"), None, None),
                (phase_state(automation=[]), None, None),
                (phase_state(review_iterations="bad"), None, None), (phase_state(stalled_run_count=True), None, None)):
            self.assertEqual(decide_control(state, evidence=evidence, runner=snapshot)["result"], "invalid_input")
        terminal = decide_control(phase_state(status="completed", review_iterations="bad", stalled_run_count=None), evidence=final_evidence(), runner=runner())
        self.assertEqual(terminal["action"], "pause_status_only")

    def test_normal_status_drift_blocks_phase_work(self):
        plan = decide_control(phase_state(configured_automation_status="ACTIVE"), evidence={"prerequisites_passed": True}, runner=runner("PAUSED"))
        self.assertEqual(plan["reason_code"], "runner_status_mismatch")

    def test_invalid_phase_prerequisites_do_not_prevent_terminal_pause(self):
        evidence = {**final_evidence(), "prerequisite_errors": [{"code": "invalid_model_policy"}]}
        self.assertEqual(decide_control(phase_state(), evidence=evidence, runner=runner())["result"], "invalid_input")
        self.assertEqual(decide_control(phase_state(status="completed"), evidence=evidence, runner=runner())["action"], "pause_status_only")

    def test_default_pause_authority_provenance_survives_normalization(self):
        explicit = default_approval_policy()
        missing_flags = {key: value for key, value in explicit.items() if not key.startswith("pause_automation_on_")}
        for raw, expected in ((None, "default_pause_automation_on_completion"), (missing_flags, "default_pause_automation_on_completion"), (explicit, "pause_automation_on_completion")):
            report = execution_policy_report(raw)
            self.assertEqual(approval_decision_for_pause_context(report, "completion")["source"], expected)
            plan = decide_control(phase_state(status="completed"), report, runner=runner())
            self.assertEqual(plan["authority"]["source"], expected)


if __name__ == "__main__":
    unittest.main()
