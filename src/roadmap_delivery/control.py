"""Pure ordered workflow decisions. Adapters execute the returned effects.

Run identity/accounting and effect execution are separate phase contracts.
No input is mutated and no filesystem, clock, process, or host API is consulted.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional

from .approval import (
    approval_decision_for_operation,
    approval_decision_for_pause_context,
    execution_policy_report,
)


PLAN_VERSION = 1
RESULT_EXIT_CODES = {
    "ready": 0, "reconcile": 0, "disabled": 0, "not_applicable": 0,
    "blocked": 1, "permission_required": 1, "invalid_input": 2,
    "unsupported": 3, "pending": 4,
}
REASONING_ORDER = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
IDENTITY_FIELDS = ("id", "project_id", "cwd", "execution_environment")


def scope_complete(state: Dict[str, Any]) -> bool:
    return (state.get("all_phases_complete") is True
            or str(state.get("status", "")).lower().replace("_", "-")
            in {"completed", "completed-pending-pause"})


def account_run_outcome(state: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Pure accounting over evidence validated by the artifact adapter.

    Event keys identify criteria/increments/causes, never log paths or timestamps.
    The adapter serializes and journals this proposal before replacing state.
    """
    if scope_complete(state):
        raise ValueError("Completed scope requires terminal closeout, not run accounting.")
    active = state.get("active_run")
    accounting = state.get("progress_accounting")
    if (not isinstance(active, dict) or not isinstance(accounting, dict)
            or accounting.get("schema_version") != 1
            or not isinstance(accounting.get("consumed_events"), list)
            or not active.get("run_id") or evidence.get("run_id") != active["run_id"]
            or evidence.get("validated") is not True
            or evidence.get("outcome") not in {"completed", "interrupted"}
            or not isinstance(evidence.get("items"), list)):
        raise ValueError("Validated outcome evidence for the active run is required.")
    for field in ("run_count", "stalled_run_count", "max_stalled_runs"):
        if type(state.get(field)) is not int or state[field] < (1 if field == "max_stalled_runs" else 0):
            raise ValueError("Invalid run counters.")
    consumed = list(accounting["consumed_events"])
    accepted = []
    for item in evidence["items"]:
        if (not isinstance(item, dict) or item.get("kind") not in {"accepted_phase_work", "criterion_satisfied", "blocker_resolved"}
                or not isinstance(item.get("event_keys"), list) or not item["event_keys"]
                or any(not isinstance(key, str) or not key for key in item["event_keys"])):
            raise ValueError("Malformed validated semantic event.")
        keys = item["event_keys"]
        if not any(key in consumed for key in keys):
            consumed.extend(keys)
            accepted.append(deepcopy(item))
    count = state["run_count"] + 1
    stalled = 0 if accepted else state["stalled_run_count"] + 1
    threshold = stalled >= state["max_stalled_runs"]
    changes = {
        "run_count": count, "stalled_run_count": stalled,
        "active_run": None, "last_completed_run_id": active["run_id"],
        "progress_accounting": {**deepcopy(accounting), "consumed_events": consumed},
    }
    repairs = [item for item in accepted if item["kind"] == "blocker_resolved"]
    if repairs:
        changes["progress_accounting"]["blocker_context"] = None
        changes.update(blocked_reason=None, status="not_started", last_blocker_repair=repairs[-1])
    elif active.get("blocked_reason"):
        changes["blocked_reason"] = active["blocked_reason"]
    if threshold:
        changes["status"] = "blocked"
        changes["stall_metadata"] = {
            "run_id": active["run_id"], "consecutive_runs": stalled,
            "threshold": state["max_stalled_runs"],
            "reason": "Consecutive unique runs without semantic progress.",
        }
        # An actionable cause is separate from the stall trigger and effect failures.
        changes["blocked_reason"] = active.get("blocked_reason") or state.get("blocked_reason") or "Stall threshold reached; inspect the unsuccessful phase attempt."
    elif accepted:
        changes["stall_metadata"] = None
    return {"schema_version": 1, "run_id": active["run_id"], "progress_detected": bool(accepted),
            "accepted_evidence": accepted, "threshold_reached": threshold,
            "proposed_state_changes": changes}


def account_verified_repair(state: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Consume external repair at a terminal stop without a new attempt/count."""
    if state.get("active_run"):
        raise ValueError("Close the unfinished attempt before repair-only reconciliation.")
    if not evidence.get("items") or any(item.get("kind") != "blocker_resolved" for item in evidence["items"]):
        raise ValueError("Repair-only reconciliation requires verified original-cause repair.")
    temporary = {**deepcopy(state), "active_run": {
        "run_id": evidence.get("run_id"), "blocked_reason": state.get("blocked_reason")}}
    outcome = account_run_outcome(temporary, evidence)
    changes = outcome["proposed_state_changes"]
    if not outcome["progress_detected"]:
        outcome["proposed_state_changes"] = {}
        outcome["threshold_reached"] = state["stalled_run_count"] >= state["max_stalled_runs"]
        return outcome
    changes["run_count"] = state["run_count"]
    changes["last_completed_run_id"] = state.get("last_completed_run_id")
    return outcome


def _policy_report(policy: Any) -> Dict[str, Any]:
    if isinstance(policy, dict) and "execution_valid" in policy:
        # Reports originate in read_approval_policy; never execute their fallback.
        return deepcopy(policy)
    return execution_policy_report(policy)


def _identity_matches(runner: Dict[str, Any]) -> bool:
    expected = runner.get("expected", {})
    observed = runner.get("observed", {})
    return bool(
        isinstance(expected, dict) and isinstance(observed, dict)
        and expected.get("id") and observed.get("id") == expected["id"]
        and all(observed.get(key) == expected[key] for key in IDENTITY_FIELDS if key in expected)
    )


def _model_matches(state: Dict[str, Any], runner: Dict[str, Any]) -> bool:
    observed = runner.get("observed", {})
    if not isinstance(observed, dict):
        return False
    required_model = state.get("required_model")
    required_reasoning = state.get("required_reasoning_effort")
    if required_model and observed.get("model") != required_model:
        return False
    if required_reasoning:
        configured = observed.get("reasoning_effort")
        if required_reasoning not in REASONING_ORDER or configured not in REASONING_ORDER:
            return False
        if REASONING_ORDER.index(configured) < REASONING_ORDER.index(required_reasoning):
            return False
    return True


def decide_control(
    state: Dict[str, Any],
    policy: Any = None,
    evidence: Optional[Dict[str, Any]] = None,
    runner: Optional[Dict[str, Any]] = None,
    *,
    event: str = "start_run",
) -> Dict[str, Any]:
    """Return one inspectable transition, its authority, changes, and effects.

    A missing raw policy is None; a malformed policy is never substituted for it.
    Runner snapshots separate expected identity from observed host readback.
    An omitted capability is unavailable. Boolean evidence is accepted only as
    validated upstream evidence; repair/review additionally require provenance.
    Outcome/recovery inputs must be artifact-validated upstream.
    """
    state = deepcopy(state)
    evidence = deepcopy({} if evidence is None else evidence)
    runner = deepcopy({} if runner is None else runner)
    plan: Dict[str, Any] = {
        "schema_version": PLAN_VERSION, "event": event,
        "stage": "phase_prerequisites", "action": "block_phase_work",
        "result": "invalid_input", "reason_code": "invalid_input",
        "authority": None, "proposed_state_changes": {}, "required_effects": [],
        "evidence_references": evidence.get("references", []) if isinstance(evidence, dict) else [],
        "extract_phase": False, "completion_claim": False,
    }

    def finish(stage: str, action: str, result: str, reason: str) -> Dict[str, Any]:
        plan.update(stage=stage, action=action, result=result, reason_code=reason)
        plan["exit_code"] = RESULT_EXIT_CODES[result]
        return plan

    if not all(isinstance(value, dict) for value in (state, evidence, runner)):
        return finish("phase_prerequisites", "block_phase_work", "invalid_input", "invalid_input")
    if (event == "operator_resume" and evidence.get("verified_repair") is not None
            and state.get("all_phases_complete") is not True
            and str(state.get("status")).replace("_", "-") not in {"completed", "completed-pending-pause"}):
        try:
            repair = account_verified_repair(state, evidence["verified_repair"])
        except (ValueError, KeyError, TypeError, AttributeError):
            return finish("terminal_reconciliation", "block_phase_work", "invalid_input", "invalid_repair_evidence")
        if repair["progress_detected"]:
            plan["proposed_state_changes"] = repair["proposed_state_changes"]
            return finish("terminal_reconciliation", "reconcile_verified_repair", "reconcile", "verified_blocker_repair")
    if (event in {"record_outcome", "recover_run"} and state.get("all_phases_complete") is not True
            and str(state.get("status")).replace("_", "-") not in {"completed", "completed-pending-pause"}):
        try:
            outcome = account_run_outcome(state, evidence.get("run_evidence", {}))
        except (ValueError, KeyError, TypeError):
            return finish("run_accounting", "block_phase_work", "invalid_input", "invalid_run_evidence")
        changes = outcome["proposed_state_changes"]
        follow_on = decide_control({**state, **changes}, policy, evidence, runner, event="start_run")
        follow_on.update(event=event, run_accounting=outcome, extract_phase=False)
        follow_on["proposed_state_changes"] = {**changes, **follow_on["proposed_state_changes"]}
        if not outcome["threshold_reached"] and not (state.get("all_phases_complete") or str(state.get("status")).startswith("completed")):
            follow_on.update(stage="run_accounting", action="record_outcome_and_stop", result="reconcile",
                             reason_code="semantic_progress" if outcome["progress_detected"] else "no_semantic_progress", exit_code=0)
        return follow_on
    status = str(state.get("status", "not_started")).lower().replace("_", "-")
    complete = state.get("all_phases_complete") is True or status in {"completed", "completed-pending-pause"}
    stage = "terminal_reconciliation" if complete else "phase_prerequisites"
    if (not isinstance(state.get("status", "not_started"), str)
            or not isinstance(state.get("all_phases_complete", False), bool)
            or (state.get("automation") is not None and not isinstance(state["automation"], dict))
            or any(not isinstance(runner.get(key, {}), dict) for key in ("expected", "observed", "capabilities"))):
        return finish(stage, "block_phase_work", "invalid_input", "invalid_snapshot")
    stalled_count = state.get("stalled_run_count", 0)
    threshold = state.get("max_stalled_runs", 2)
    if not complete and (type(stalled_count) is not int or stalled_count < 0 or type(threshold) is not int or threshold < 1):
        return finish("terminal_reconciliation" if complete else "phase_prerequisites", "block_phase_work", "invalid_input", "invalid_counters")
    stalled = not complete and stalled_count >= threshold
    report = _policy_report(policy)
    pause_context = "completion" if complete else "stall"
    authority = approval_decision_for_pause_context(report, pause_context)
    valid_policy = authority.get("reason_code") != "invalid_policy"
    observed = runner.get("observed", {})
    capabilities = runner.get("capabilities", {})
    if not isinstance(observed, dict) or not isinstance(capabilities, dict):
        return finish("terminal_reconciliation" if complete or stalled else "phase_prerequisites", "block_phase_work", "invalid_input", "invalid_runner")

    # Terminal priority intentionally bypasses the phase model/review gates.
    if complete or stalled:
        stage = "terminal_reconciliation"
        plan["authority"] = authority
        plan["required_effects"] = [{"operation": "write_local_alert", "context": pause_context}]
        if complete:
            plan["proposed_state_changes"]["status"] = "completed_pending_pause"
        else:
            plan["proposed_state_changes"]["status"] = "blocked"
        manual = evidence.get("manual_pause_authority", {})
        manual_authorized = bool(
            isinstance(manual, dict) and manual.get("authorized") is True
            and manual.get("operation") == "pause_saved_automation"
            and manual.get("runner_id") == runner.get("expected", {}).get("id")
            and manual.get("source")
        )
        if manual_authorized:
            plan["authority"] = {"decision": "allowed", "source": manual["source"], "context": "manual"}
        if not valid_policy and not manual_authorized:
            return finish(stage, "record_policy_blocker", "invalid_input", "invalid_policy")
        if stalled and not complete and event == "operator_resume" and evidence.get("fresh_budget_authority"):
            budget = evidence["fresh_budget_authority"]
            if isinstance(budget, dict) and budget.get("authorized") is True and budget.get("source") and _identity_matches(runner):
                plan["required_effects"] = [{"operation": "archive_attempt_epoch", "authority": budget["source"]}]
                plan["proposed_state_changes"]["stalled_run_count"] = 0
                return finish(stage, "archive_epoch_and_activate", "reconcile", "explicit_fresh_budget")
        final_gates = bool(
            evidence.get("final_verification_passed") is True
            and evidence.get("delivered_review") is True
            and (evidence.get("final_deep_review_prompt_present") is True or evidence.get("human_waiver_recorded") is True)
        )
        if runner.get("kind") == "manual":
            if complete and final_gates:
                plan["proposed_state_changes"]["status"] = "completed"
                plan["completion_claim"] = True
            return finish(stage, "record_not_applicable", "not_applicable", "manual_run")
        if authority.get("decision") == "disabled" and not manual_authorized:
            return finish(stage, "record_disabled", "disabled", "context_pause_disabled")
        if not _identity_matches(runner):
            return finish(stage, "record_mismatch", "invalid_input", "runner_identity_mismatch")
        if capabilities.get("readback") is not True:
            return finish(stage, "record_unsupported", "unsupported", "pause_capability_unavailable")
        if observed.get("status") == "PAUSED":
            if complete and final_gates:
                plan["proposed_state_changes"]["status"] = "completed"
                plan["completion_claim"] = True
            return finish(stage, "record_receipt", "reconcile", "paused_readback")
        if capabilities.get("status_update") is not True:
            return finish(stage, "record_unsupported", "unsupported", "pause_capability_unavailable")
        if observed.get("status") != "ACTIVE":
            return finish(stage, "record_pending", "pending", "pause_readback_unknown")
        if evidence.get("pause_request_accepted") is True:
            return finish(stage, "record_pending", "pending", "pause_unconfirmed")
        plan["required_effects"].append({
            "operation": "pause_status_only", "context": "manual" if manual_authorized else pause_context,
            "runner_id": observed["id"], "readback_required": True,
            "preserve_non_status_settings": True,
        })
        if complete and not final_gates:
            return finish(stage, "reconcile_completion", "reconcile", "completion_evidence_incomplete")
        return finish(stage, "pause_status_only" if complete else "alert_and_pause", "ready", "terminal_pause_required")

    if event not in {"start_run", "operator_resume", "phase_review", "advance_phase"}:
        return finish("phase_prerequisites", "block_phase_work", "invalid_input", "unknown_event")
    if not valid_policy:
        return finish("blocked_remediation" if status == "blocked" else "phase_prerequisites", "record_required_action" if status == "blocked" else "block_phase_work", "invalid_input", "invalid_policy")

    expected_status = state.get("configured_automation_status") or (state.get("automation") or {}).get("status")
    if expected_status == "PAUSED" and observed.get("status") == "ACTIVE":
        expected = runner.get("expected", {})
        guards = observed.get("prompt_guards", {})
        matching = bool(
            _identity_matches(runner) and _model_matches(state, runner) and not evidence.get("prerequisite_errors")
            and all(expected.get(key) for key in IDENTITY_FIELDS)
            and isinstance(guards, dict)
            and all(guards.get(key) is True for key in ("state_first", "terminal", "blocked_remediation"))
        )
        if not matching:
            return finish("intentional_activation", "record_mismatch", "blocked", "activation_configuration_mismatch")
        plan["proposed_state_changes"] = {"configured_automation_status": "ACTIVE", "activation_reconciliation_required": True}
        return finish("intentional_activation", "reconcile_activation", "reconcile", "intentional_operator_activation")

    if status == "blocked":
        blocker = evidence.get("blocker_class", "unclassified")
        verified = bool(
            evidence.get("repair_verified") is True and evidence.get("repair_verification")
            and state.get("blocked_reason") and evidence.get("repaired_blocker") == state["blocked_reason"]
        )
        if verified:
            plan["proposed_state_changes"] = {"blocked_reason": None, "status": "not_started"}
            return finish("blocked_remediation", "clear_verified_cause", "reconcile", "verified_blocker_repair")
        if blocker == "local-repairable" or (blocker == "automation-config" and evidence.get("repair_authorized") is True):
            return finish("blocked_remediation", "repair_blocker", "reconcile", "repair_before_delivery")
        return finish("blocked_remediation", "record_required_action", "blocked", "blocker_requires_action")

    if evidence.get("prerequisite_errors"):
        return finish("phase_prerequisites", "block_phase_work", "invalid_input", "invalid_prerequisite_evidence")
    # Optional upgrade decisions remain visible, but never gate terminal pause.
    migration = evidence.get("migration_decision")
    if migration is not None:
        if not isinstance(migration, dict) or migration.get("decision") not in {"pending", "declined", "approved"}:
            return finish("phase_prerequisites", "block_phase_work", "invalid_input", "invalid_migration_decision")
        plan["migration_decision"] = deepcopy(migration)
        plan["migration_ask_again"] = False
    resolution = evidence.get("model_target_resolution")
    if resolution is not None:
        if (not isinstance(resolution, dict) or resolution.get("status") != "resolved"
                or resolution.get("errors") or not isinstance(resolution.get("target"), dict)
                or not isinstance(resolution["target"].get("model"), str)
                or not resolution["target"]["model"].strip()
                or resolution["target"].get("reasoning_effort") not in REASONING_ORDER):
            return finish("phase_prerequisites", "block_phase_work", "invalid_input", "invalid_model_target")
        state["required_model"] = resolution["target"].get("model")
        state["required_reasoning_effort"] = resolution["target"].get("reasoning_effort")
    for key, default, minimum in (("review_iterations", 0, 0), ("max_review_iterations", 3, 1)):
        value = state.get(key, default)
        if type(value) is not int or value < minimum:
            return finish("phase_prerequisites", "block_phase_work", "invalid_input", "invalid_review_counters")
    if not _model_matches(state, runner):
        return finish("phase_prerequisites", "block_phase_work", "blocked", "phase_model_mismatch")
    if runner and runner.get("kind") != "manual" and not _identity_matches(runner):
        return finish("phase_prerequisites", "block_phase_work", "blocked", "runner_identity_mismatch")
    if expected_status and runner.get("kind") != "manual" and observed.get("status") != expected_status:
        return finish("phase_prerequisites", "block_phase_work", "blocked", "runner_status_mismatch")
    authority = approval_decision_for_operation(report.get("operations", {}), "edit_phase_owned_files")
    plan["authority"] = authority
    if authority["decision"] != "allowed":
        return finish("phase_prerequisites", "block_phase_work", "permission_required", "phase_edit_authority_required")
    if evidence.get("prerequisites_passed") is not True:
        return finish("phase_prerequisites", "check_prerequisites", "reconcile", "phase_prerequisites_unverified")

    if event in {"phase_review", "advance_phase"}:
        verdict = evidence.get("review_verdict")
        if verdict == "needs-fix":
            if state.get("review_iterations", 0) >= state.get("max_review_iterations", 3):
                return finish("delivery_review", "record_required_action", "blocked", "review_iterations_exhausted")
            return finish("delivery_review", "fix_current_phase", "ready", "current_phase_findings")
        passed = bool(
            verdict == "delivered" and evidence.get("acceptance_passed") is True
            and evidence.get("verification_passed") is True and evidence.get("review_fresh") is True
            and evidence.get("review_file") and evidence.get("review_phase") == state.get("current_phase")
        )
        if not passed:
            return finish("delivery_review", "review_current_phase", "blocked", "delivery_gate_incomplete")
        if event == "advance_phase":
            next_phase = evidence.get("next_numbered_phase")
            plan["proposed_state_changes"] = {"current_phase": next_phase or "finalization", "status": "not_started"}
            return finish("next_phase_or_finalization", "plan_next_and_stop" if next_phase else "prepare_finalization", "ready", "delivered_review")
        return finish("delivery_review", "plan_advancement", "ready", "delivered_review")
    plan["extract_phase"] = True
    return finish("delivery_review", "deliver_current_phase", "ready", "phase_prerequisites_passed")
