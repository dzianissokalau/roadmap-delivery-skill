"""Offline behavioral matrix for constrained targets and durable provenance."""
import copy
import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from roadmap_delivery.adaptive import (
    adaptive_decision_fingerprint, adaptive_provenance, classify_run_quality_from_state, persisted_adaptive_target,
    resolve_adaptive_action, validated_flawless_streak,
)
from roadmap_delivery.policy import resolve_model_target, resolve_phase_target
from roadmap_delivery.control import decide_control
from roadmap_delivery import reports
from tests import test_adaptive_model_policy as adaptive_tests
from tests.test_helper_scripts import DeliveryFixture


def policy():
    return {
        "schema_version": 1, "policy_version": "fixture-v1", "max_stalled_runs": 2,
        "notification": {"mode": "alert_file", "fallback": "alert_file"},
        "defaults": {"model": "small", "reasoning_effort": "high"},
        "phases": {"2": {"model": "small", "reasoning_effort": "high"}},
        "adaptive_model_policy": {
            "enabled": True, "floors": {"min_reasoning_effort": "high"},
            "caps": {"allowed_models": ["small", "large"], "max_reasoning_effort": "xhigh"},
            "escalation": {"model": "large", "reasoning_effort": "xhigh"},
            "deescalation": {"model": "small", "reasoning_effort": "low"},
            "deescalate_after_flawless_runs": 1,
        },
    }


def state():
    return {"current_phase": "Phase 1 - Fixture", "last_completed_run_id": "run-1",
            "last_run_quality": "verification_failed", "review_iterations": 1,
            "last_verification": {"phase": "Phase 1 - Fixture", "run_id": "run-1", "status": "passed"},
            "last_review": {"phase": "Phase 1 - Fixture", "run_id": "run-1", "verdict": "delivered", "iteration": 1},
            "stalled_run_count": 0, "max_stalled_runs": 2}


def saved_target(p, s, target=None):
    source = s["current_phase"]
    s["last_adaptive_action"] = {"action": "escalate", "run_quality": "flawless",
        "target_phase": "Phase 2 - Fixture", "target": target or {"model": "large", "reasoning_effort": "xhigh"},
        "provenance": adaptive_provenance(p, s, source, "Phase 2 - Fixture")}
    s["last_adaptive_action"]["decision_fingerprint"] = adaptive_decision_fingerprint(s["last_adaptive_action"])
    s["current_phase"] = "Phase 2 - Fixture"
    return s


class ModelTargetConstraintTests(unittest.TestCase):
    def test_direct_resolver_requires_caps_even_with_valid_base(self):
        p = policy()
        p["adaptive_model_policy"].pop("caps")
        result = resolve_model_target(p, base_target=p["defaults"])
        self.assertIsNone(result["target"])
        self.assertIn("missing_adaptive_caps", {e["code"] for e in result["errors"]})

    def test_resolution_matrix_default_override_and_all_quality_paths(self):
        p = policy()
        for phase, quality, model, effort in (
            ("unknown", "flawless", "small", "high"),
            ("2", "verification_failed", "large", "xhigh"),
            ("2", "blocked_human_required", "small", "high"),
            ("2", "completion_closeout_failed", "small", "high"),
            ("2", "delivered_with_fixes", "large", "xhigh"),
            ("2", "blocked_local_repairable", "small", "high"),
        ):
            with self.subTest(phase=phase, quality=quality):
                b = resolve_phase_target(p, phase)
                result = resolve_adaptive_action(p, base_model=b["model"],
                    base_reasoning_effort=b["reasoning_effort"], run_quality=quality)
                self.assertEqual(result["errors"], [])
                self.assertEqual(result["target"], {"model": model, "reasoning_effort": effort})
                self.assertEqual(result["resolution"]["host_support"], "unknown")
        p["phases"]["2"]["reasoning_effort"] = "xhigh"
        action = resolve_adaptive_action(p, base_model="small", base_reasoning_effort="xhigh", run_quality="flawless")
        self.assertEqual(action["target"]["reasoning_effort"], "xhigh")
        self.assertEqual(action["action"], "none_at_floor")

    def test_conflicts_invalid_values_and_disabled_paths_fail_closed(self):
        mutations = (
            lambda p: p["adaptive_model_policy"]["caps"].update(max_reasoning_effort="medium"),
            lambda p: p["defaults"].update(model="outside"),
            lambda p: p["defaults"].update(reasoning_effort="warp"),
            lambda p: p["phases"]["2"].update(model=""),
            lambda p: p["adaptive_model_policy"]["escalation"].update(model="outside"),
            lambda p: p["adaptive_model_policy"]["escalation"].update(reasoning_effort="ultra"),
            lambda p: p.update(adaptive_model_policy="invalid"),
            lambda p: p["adaptive_model_policy"].update(enabled="false"),
            lambda p: p["adaptive_model_policy"]["floors"].update(min_reasoning_effort="warp"),
        )
        for mutation in mutations:
            p = policy(); mutation(p)
            b = resolve_phase_target(p, "2") if p["defaults"]["model"] == "small" and p["defaults"]["reasoning_effort"] == "high" else resolve_phase_target(p, "unknown")
            action = resolve_adaptive_action(p, base_model=b["model"], base_reasoning_effort=b["reasoning_effort"], run_quality="verification_failed")
            self.assertTrue(action["errors"])
            self.assertIsNone(action["target"])
            self.assertEqual(action["action"], "blocked_by_policy")
        p = policy(); p["adaptive_model_policy"]["enabled"] = False
        action = resolve_adaptive_action(p, base_model="outside", base_reasoning_effort="high", run_quality="flawless")
        self.assertIsNone(action["target"])

    def test_floor_aliases_are_combined_and_input_is_not_mutated(self):
        p = policy(); p["adaptive_model_policy"]["floors"]["reasoning_effort"] = "xhigh"
        original = copy.deepcopy(p)
        r = resolve_model_target(p, base_target=p["defaults"], proposal={"reasoning_effort": "low"})
        self.assertEqual(r["target"]["reasoning_effort"], "xhigh")
        self.assertEqual(p, original)

    def test_host_capabilities_and_metadata_limits_are_explicit(self):
        p = policy(); p["adaptive_model_policy"]["caps"].update(allowed_providers=["vendor"], allowed_cost_classes=["standard"])
        forged = {"model": "small", "reasoning_effort": "high", "provider": "vendor", "cost_class": "standard"}
        unknown = resolve_model_target(p, base_target=p["defaults"], proposal=forged)
        self.assertIsNone(unknown["target"])
        self.assertEqual(unknown["metadata_limits"]["allowed_providers"], "unresolved")
        metadata = {"trusted": True, "source": "isolated-host-fixture", "models": {
            "small": {"reasoning_efforts": ["xhigh"], "provider": "vendor", "cost_class": "standard", "rank": 1},
            "large": {"reasoning_efforts": ["high", "xhigh"], "provider": "vendor", "cost_class": "premium", "rank": 2}}}
        r = resolve_model_target(p, base_target=p["defaults"], host_capabilities=metadata)
        self.assertEqual(r["target"]["reasoning_effort"], "xhigh")
        self.assertEqual(r["host_support"], "supported")
        self.assertEqual(r["metadata_limits"]["allowed_cost_classes"], "enforced")
        metadata["trusted"] = False
        self.assertIsNone(resolve_model_target(p, base_target=p["defaults"], host_capabilities=metadata)["target"])
        metadata["trusted"] = True
        p["adaptive_model_policy"]["floors"]["model"] = "large"
        self.assertIn("target_model_below_floor", {e["code"] for e in resolve_model_target(p, base_target=p["defaults"], host_capabilities=metadata)["errors"]})
        p["adaptive_model_policy"]["caps"]["max_reasoning_effort"] = "high"
        self.assertIsNone(resolve_model_target(p, base_target=p["defaults"], host_capabilities=metadata)["target"])

    def test_persisted_targets_require_current_run_policy_phase_and_evidence(self):
        p = policy(); s = saved_target(p, state())
        self.assertEqual(persisted_adaptive_target(s, s["current_phase"], p)["target"]["model"], "large")
        mutations = (
            lambda p, s: p.update(policy_version="v2"),
            lambda p, s: p["adaptive_model_policy"]["caps"].update(max_reasoning_effort="high"),
            lambda p, s: s["last_adaptive_action"]["provenance"]["source_evidence"].update(last_completed_run_id="run-2"),
            lambda p, s: s["last_review"].update(verdict="needs-fix"),
            lambda p, s: s["last_adaptive_action"].update(target_phase="Phase 3 - Fixture"),
            lambda p, s: s["last_adaptive_action"].pop("provenance"),
            lambda p, s: s["last_adaptive_action"].update(run_quality="verification_failed"),
            lambda p, s: s["last_adaptive_action"]["target"].update(model="small"),
            lambda p, s: s["last_adaptive_action"].update(capabilities_fingerprint="changed"),
        )
        for mutation in mutations:
            pp, ss = copy.deepcopy(p), copy.deepcopy(s); mutation(pp, ss)
            self.assertIsNone(persisted_adaptive_target(ss, ss["current_phase"], pp)["target"])
        for target in ({"model": "outside", "reasoning_effort": "high"}, {"model": "small", "reasoning_effort": "warp"}):
            ss = saved_target(p, state(), target)
            self.assertEqual(persisted_adaptive_target(ss, ss["current_phase"], p)["status"], "invalid_policy")
        ss = saved_target(p, state(), {"model": "small", "reasoning_effort": "low"})
        self.assertEqual(persisted_adaptive_target(ss, ss["current_phase"], p)["target"]["reasoning_effort"], "high")

    def test_quality_and_streak_do_not_trust_stale_scalars(self):
        p, s = policy(), state()
        self.assertEqual(classify_run_quality_from_state(s), "flawless")
        self.assertEqual(classify_run_quality_from_state(s, blocker_class="permission-gated"), "blocked_human_required")
        s.pop("last_verification")
        self.assertEqual(classify_run_quality_from_state(s), "blocked_human_required")
        s["last_verification"] = {"phase": s["current_phase"], "run_id": "run-1", "status": "failed"}
        s["last_run_quality"] = "flawless"
        self.assertEqual(classify_run_quality_from_state(s), "verification_failed")
        s["last_review"]["phase"] = "Phase 0 - Old"; s["last_verification"]["phase"] = "Phase 0 - Old"
        self.assertEqual(classify_run_quality_from_state(s), "blocked_human_required")
        fresh = state()
        fresh["active_run"] = {"run_id": "run-2", "phase": fresh["current_phase"]}
        self.assertEqual(classify_run_quality_from_state(fresh), "blocked_human_required")
        s = saved_target(p, state()); s["adaptive_flawless_streak"] = 2
        self.assertEqual(validated_flawless_streak(s, p, s["current_phase"]), 0)
        s["last_adaptive_action"]["next_flawless_streak"] = 2
        s["last_adaptive_action"]["decision_fingerprint"] = adaptive_decision_fingerprint(s["last_adaptive_action"])
        self.assertEqual(validated_flawless_streak(s, p, s["current_phase"]), 2)
        p["policy_version"] = "v2"
        self.assertEqual(validated_flawless_streak(s, p, s["current_phase"]), 0)

    def test_next_phase_evidence_preserves_bound_source_and_capabilities(self):
        p, s = policy(), state()
        s["last_verification"]["status"] = "failed"
        metadata = {"trusted": True, "source": "test-host", "models": {
            name: {"reasoning_efforts": ["high", "xhigh"], "provider": "vendor"}
            for name in ("small", "large")}}
        p["adaptive_model_policy"]["caps"]["allowed_providers"] = ["vendor"]
        action = resolve_adaptive_action(p, base_model="small", base_reasoning_effort="high",
            run_quality=classify_run_quality_from_state(s), host_capabilities=metadata,
            provenance=adaptive_provenance(p, s, s["current_phase"], "Phase 2 - Fixture"))
        action["target_phase"] = "Phase 2 - Fixture"
        s.update(last_adaptive_action=action, current_phase="Phase 2 - Fixture")
        for stage in ("start", "verification", "review", "finish"):
            with self.subTest(stage=stage):
                s["active_run"] = {"run_id": "run-2", "phase": s["current_phase"]}
                if stage != "start": s["last_verification"] = {"phase": s["current_phase"], "run_id": "run-2", "status": "passed"}
                if stage in ("review", "finish"): s["last_review"] = {"phase": s["current_phase"], "run_id": "run-2", "verdict": "delivered"}
                if stage == "finish": s.update(active_run=None, last_completed_run_id="run-2")
                self.assertEqual(persisted_adaptive_target(s, s["current_phase"], p)["target"]["model"], "large")
                from roadmap_delivery.validation import validate_model_policy
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "policy.json"; path.write_text(json.dumps(p))
                    errors = []
                    result = validate_model_policy(path, s, {"model": "large", "reasoning_effort": "xhigh"}, errors, [])
                    self.assertEqual(errors, [])
                    self.assertEqual(result["persisted_target_status"], "resolved")

    def test_missing_or_incoherent_run_identity_cannot_deescalate(self):
        for run_id in (None, "", "different-run"):
            s = state(); s["last_completed_run_id"] = run_id
            s["last_verification"]["run_id"] = "unrelated-run"
            quality = classify_run_quality_from_state(s)
            self.assertEqual(quality, "blocked_human_required")
            self.assertEqual(resolve_adaptive_action(policy(), base_model="large", base_reasoning_effort="xhigh", run_quality=quality)["action"], "none_human_gated")

    def test_same_bound_decision_reuses_input_streak_only_with_matching_provenance(self):
        p, s = policy(), state()
        p["adaptive_model_policy"]["deescalate_after_flawless_runs"] = 2
        proof = adaptive_provenance(p, s, s["current_phase"], "Phase 2 - Fixture")
        action = resolve_adaptive_action(p, base_model="large", base_reasoning_effort="high",
            run_quality="flawless", flawless_streak=1, provenance=proof)
        action["target_phase"] = "Phase 2 - Fixture"
        def resolve(previous, provenance=proof, policy_value=p, metadata=None):
            return resolve_adaptive_action(policy_value, base_model="large", base_reasoning_effort="high",
                run_quality="flawless", flawless_streak=0, provenance=provenance,
                host_capabilities=metadata, previous_action=previous)
        replayed = resolve(action)
        self.assertEqual(replayed, {k: v for k, v in action.items() if k != "target_phase"})
        altered = copy.deepcopy(action); altered["previous_flawless_streak"] = 4
        self.assertEqual(resolve(altered)["previous_flawless_streak"], 0)
        s["last_completed_run_id"] = "different-run"
        self.assertEqual(resolve(action, adaptive_provenance(p, s, s["current_phase"], "Phase 2 - Fixture"))["previous_flawless_streak"], 0)
        changed_policy = copy.deepcopy(p); changed_policy["policy_version"] = "new-version"
        self.assertEqual(resolve(action, policy_value=changed_policy)["previous_flawless_streak"], 0)
        metadata = {"trusted": True, "source": "new-readback", "models": {
            name: {"reasoning_efforts": ["high"]} for name in ("small", "large")}}
        self.assertEqual(resolve(action, metadata=metadata)["previous_flawless_streak"], 0)

    def test_configured_capabilities_check_actual_values_without_cost_downgrades(self):
        from roadmap_delivery.validation import validate_model_policy
        p = policy(); p["adaptive_model_policy"]["caps"]["max_reasoning_effort"] = "ultra"
        metadata = {"trusted": True, "source": "test-host", "models": {
            "small": {"reasoning_efforts": ["high"]}}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"; path.write_text(json.dumps(p))
            for efforts, expected in ((["high"], "unsupported"), (["high", "xhigh"], "supported")):
                metadata["models"]["small"]["reasoning_efforts"] = efforts
                errors = []
                result = validate_model_policy(path, state(), {"model": "small", "reasoning_effort": "xhigh"},
                    errors, [], host_capabilities=metadata)
                self.assertEqual(result["configured_host_support"], expected)
                self.assertEqual(bool(errors), expected == "unsupported")
                if errors:
                    self.assertEqual(errors[0]["code"], "configured_target_host_unsupported")
            result = validate_model_policy(path, state(), {"model": "small", "reasoning_effort": "xhigh"}, [], [])
            self.assertEqual(result["configured_host_support"], "unknown")

    def test_terminal_control_precedes_invalid_target(self):
        p = {"status": "completed", "all_phases_complete": True}
        r = decide_control(p, evidence={"model_target_resolution": {"status": "invalid_policy"}}, runner={"kind": "manual"})
        self.assertEqual(r["stage"], "terminal_reconciliation")
        r = decide_control({"status": "not_started"}, evidence={"model_target_resolution": {"status": "invalid_policy"}}, runner={"kind": "manual"})
        self.assertEqual(r["reason_code"], "invalid_model_target")
        r = decide_control({"status": "not_started"}, evidence={"model_target_resolution": {"status": "resolved", "target": {}}}, runner={"kind": "manual"})
        self.assertEqual(r["reason_code"], "invalid_model_target")


class ConstraintEntrypointTests(unittest.TestCase):
    run_plan = adaptive_tests.AdaptiveModelPolicyTests.run_plan
    run_validate = adaptive_tests.AdaptiveModelPolicyTests.run_validate
    error_codes = adaptive_tests.AdaptiveModelPolicyTests.error_codes

    def source_plan(self, fixture, phase, metadata_file=None):
        args = argparse.Namespace(repo_root=str(fixture.repo_root), roadmap_slug=fixture.slug,
            automation_id=fixture.automation_id, delivered_phase=phase, simulate_update_failure=None,
            capabilities_file=str(metadata_file) if metadata_file else None)
        with patch.object(reports, "AUTOMATIONS_DIR", fixture.home / ".codex/automations"):
            plan, errors = reports.retarget_build_plan(args)
        self.assertEqual(errors, [])
        return plan

    def test_retarget_retries_after_state_persistence_replay_the_same_completed_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = policy(); p["defaults"]["model"] = "large"; p["phases"] = {}
            p["adaptive_model_policy"]["deescalate_after_flawless_runs"] = 2
            f = DeliveryFixture(tmp, write_model_policy=True, policy_text=json.dumps(p),
                policy_model="large", policy_reasoning="high", automation_model="large", automation_reasoning="high")
            road = f.repo_root / "roadmaps" / f.roadmap_filename
            road.write_text(road.read_text() + "\n## Phase 2 - Fixture\n\nFixture.\n\n## Phase 3 - Fixture\n\nFixture.\n")
            sp = f.state_dir / "delivery_state.json"; s = json.loads(sp.read_text()); s.update(state())
            sp.write_text(json.dumps(s))
            first = self.source_plan(f, "Phase 1 - Fixture")
            s.update(first["state_updates"])
            s.update(last_completed_run_id="run-2",
                last_verification={"phase": s["current_phase"], "run_id": "run-2", "status": "passed"},
                last_review={"phase": s["current_phase"], "run_id": "run-2", "verdict": "delivered", "iteration": 1})
            sp.write_text(json.dumps(s))
            second = self.source_plan(f, "Phase 2 - Fixture")
            self.assertEqual(second["adaptive_action"]["action"], "deescalate")
            self.assertEqual(second["target"]["model"], "small")
            for _ in range(3):
                s.update(second["state_updates"]); sp.write_text(json.dumps(s))
                repeated = self.source_plan(f, "Phase 2 - Fixture")
                self.assertEqual(repeated["adaptive_action"], second["adaptive_action"])
                self.assertEqual(repeated["state_updates"], second["state_updates"])
            s["last_review"]["iteration"] = 2; sp.write_text(json.dumps(s))
            changed = self.source_plan(f, "Phase 2 - Fixture")
            self.assertEqual(changed["adaptive_action"]["action"], "escalate")
            self.assertNotEqual(changed["adaptive_action"]["decision_fingerprint"], second["adaptive_action"]["decision_fingerprint"])

    def test_unsupported_configured_reasoning_requires_retarget_even_above_floor(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = policy()
            f = DeliveryFixture(tmp, write_model_policy=True, policy_text=json.dumps(p),
                policy_model="small", policy_reasoning="high", automation_model="small", automation_reasoning="xhigh")
            road = f.repo_root / "roadmaps" / f.roadmap_filename
            road.write_text(road.read_text() + "\n## Phase 2 - Fixture\n\nFixture.\n")
            metadata = {"trusted": True, "source": "test-host", "models": {"small": {"reasoning_efforts": ["high"]}}}
            path = Path(tmp) / "metadata.json"; path.write_text(json.dumps(metadata))
            result = self.source_plan(f, "Phase 1 - Fixture", path)
            self.assertEqual(result["automation"]["configured_host_support"], "unsupported")
            self.assertTrue(result["retarget"]["reasoning_update_required"])
            self.assertFalse(result["retarget"]["reasoning_downgrade_not_required"])
            self.assertEqual(result["target"]["reasoning_effort"], "high")
            metadata["models"]["small"]["reasoning_efforts"].append("xhigh"); path.write_text(json.dumps(metadata))
            result = self.source_plan(f, "Phase 1 - Fixture", path)
            self.assertEqual(result["retarget"]["status"], "not_needed")

    def test_cross_model_retarget_preserves_reasoning_only_when_destination_supports_it(self):
        for efforts in (["high"], ["high", "xhigh"]):
            with self.subTest(destination_efforts=efforts), tempfile.TemporaryDirectory() as tmp:
                p = policy(); p["adaptive_model_policy"]["enabled"] = False
                p["phases"]["2"]["model"] = "large"
                f = DeliveryFixture(tmp, write_model_policy=True, policy_text=json.dumps(p),
                    policy_model="small", policy_reasoning="high", automation_model="small", automation_reasoning="xhigh")
                road = f.repo_root / "roadmaps" / f.roadmap_filename
                road.write_text(road.read_text() + "\n## Phase 2 - Fixture\n\nFixture.\n")
                metadata = {"trusted": True, "source": "test-host", "models": {
                    "small": {"reasoning_efforts": ["high", "xhigh"]},
                    "large": {"reasoning_efforts": efforts}}}
                path = Path(tmp) / "metadata.json"; path.write_text(json.dumps(metadata))
                result = self.source_plan(f, "Phase 1 - Fixture", path)
                self.assertEqual(result["automation"]["configured_host_support"], "supported")
                self.assertEqual(result["target"]["model"], "large")
                self.assertEqual(result["target"]["reasoning_effort"], "high")
                self.assertTrue(result["retarget"]["model_update_required"])
                self.assertEqual(result["retarget"]["reasoning_update_required"], "xhigh" not in efforts)
                self.assertEqual(result["retarget"]["reasoning_downgrade_not_required"], "xhigh" in efforts)

    def test_generated_planner_enforces_operator_metadata_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = policy()
            p["adaptive_model_policy"]["caps"].update(allowed_providers=["vendor"], allowed_cost_classes=["standard"])
            f = DeliveryFixture(tmp, write_model_policy=True, policy_text=json.dumps(p),
                policy_model="small", policy_reasoning="high", automation_model="small", automation_reasoning="xhigh")
            road = f.repo_root / "roadmaps" / f.roadmap_filename
            road.write_text(road.read_text() + "\n## Phase 2 - Fixture\n\nFixture.\n")
            metadata = {"trusted": True, "source": "offline-operator-fixture", "models": {
                "small": {"reasoning_efforts": ["high", "xhigh"], "provider": "vendor", "cost_class": "standard"}}}
            path = Path(tmp) / "metadata.json"
            path.write_text(json.dumps(metadata))
            r = self.run_plan(f, "--delivered-phase", "Phase 1 - Fixture", "--capabilities-file", str(path))
            self.assertEqual(r["retarget"]["status"], "not_needed")
            self.assertEqual(r["adaptive_action"]["resolution"]["metadata_limits"]["allowed_providers"], "enforced")
            metadata["models"]["small"]["cost_class"] = "premium"
            path.write_text(json.dumps(metadata))
            r = self.run_plan(f, "--delivered-phase", "Phase 1 - Fixture", "--capabilities-file", str(path), allowed_returncodes=(1,))
            self.assertEqual(r["state_updates"], {})
            self.assertEqual(r["retarget"]["status"], "invalid_policy")

    def test_planner_and_validation_share_constraints_and_preserve_higher_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = policy()
            f = DeliveryFixture(tmp, write_model_policy=True, policy_text=json.dumps(p), policy_model="small", policy_reasoning="high", automation_model="small", automation_reasoning="xhigh")
            road = f.repo_root / 'roadmaps' / f.roadmap_filename
            road.write_text(road.read_text() + '\n## Phase 2 - Fixture\n\nFixture.\n')
            result = self.run_plan(f, '--delivered-phase', 'Phase 1 - Fixture')
            self.assertEqual(result['target']['reasoning_effort'], 'high')
            self.assertEqual(result['retarget']['status'], 'not_needed')
            self.assertTrue(result['retarget']['reasoning_downgrade_not_required'])
            self.assertEqual(result['adaptive_action']['resolution']['host_support'], 'unknown')
            p['adaptive_model_policy']['caps']['max_reasoning_effort'] = 'medium'
            (f.state_dir / 'phase_model_policy.json').write_text(json.dumps(p))
            result = self.run_plan(f, '--delivered-phase', 'Phase 1 - Fixture', allowed_returncodes=(1,))
            self.assertEqual(result['retarget']['status'], 'invalid_policy')
            self.assertEqual(result['state_updates'], {})
            self.assertIsNone(result['adaptive_action']['target'])
            validation = self.run_validate(f)
            self.assertIn('target_floor_above_cap', self.error_codes(validation))

    def test_bound_persisted_target_validation_and_version_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = policy(); f = DeliveryFixture(tmp, current_phase='Phase 2 - Fixture', write_model_policy=True,
                policy_text=json.dumps(p), policy_model='small', policy_reasoning='high', automation_model='large', automation_reasoning='xhigh')
            sp = f.state_dir / 'delivery_state.json'; ss = json.loads(sp.read_text())
            saved = saved_target(p, state())
            ss.update(saved); sp.write_text(json.dumps(ss))
            result = self.run_validate(f)
            self.assertEqual(result['model_policy']['required_model'], 'large')
            self.assertEqual(result['model_policy']['persisted_target_status'], 'resolved')
            p['policy_version'] = 'v2'; (f.state_dir / 'phase_model_policy.json').write_text(json.dumps(p))
            result = self.run_validate(f)
            self.assertEqual(result['model_policy']['required_model'], 'small')
            self.assertEqual(result['model_policy']['persisted_target_status'], 'ignored_stale')


if __name__ == '__main__':
    unittest.main()
