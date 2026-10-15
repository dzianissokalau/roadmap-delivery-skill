"""Adaptive model policy helpers for roadmap delivery runs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Sequence

from .policy import REASONING_ORDER, policy_fingerprint, resolve_model_target, resolve_phase_target


RUN_QUALITIES = (
    "flawless",
    "delivered_with_fixes",
    "verification_failed",
    "review_needs_fix",
    "blocked_local_repairable",
    "blocked_human_required",
    "stalled",
    "retarget_failed",
    "completion_closeout_failed",
)

DEFAULT_ESCALATE_ON = (
    "delivered_with_fixes",
    "verification_failed",
    "review_needs_fix",
    "stalled",
    "retarget_failed",
)

DEFAULT_HUMAN_GATED_QUALITIES = (
    "blocked_human_required",
    "completion_closeout_failed",
)

LOCAL_REPAIRABLE_BLOCKERS = {"local-repairable", "local_repairable", "automation-config", "automation_config"}
HUMAN_GATED_BLOCKERS = {"permission-gated", "permission_gated", "external-decision", "external_decision", "destructive-risk", "destructive_risk"}


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def is_run_quality(value: Any) -> bool:
    return _normalized(value) in {item.replace("_", "-") for item in RUN_QUALITIES}


def normalize_run_quality(value: Any) -> Optional[str]:
    normalized = _normalized(value)
    for quality in RUN_QUALITIES:
        if normalized == quality.replace("_", "-"):
            return quality
    return None


def classify_run_quality(
    *,
    verification_status: Any = None,
    review_verdict: Any = None,
    fix_iterations: Any = 0,
    blocker_class: Any = None,
    stalled: bool = False,
    retarget_status: Any = None,
    completion_closeout_failed: bool = False,
) -> str:
    """Classify a run outcome using the durable evidence collected by the gate."""

    retarget = _normalized(retarget_status)
    blocker = _normalized(blocker_class)
    verification = _normalized(verification_status)
    verdict = _normalized(review_verdict)

    if completion_closeout_failed:
        return "completion_closeout_failed"
    if retarget in {"failed", "retarget-failed", "retarget-failed-alert"}:
        return "retarget_failed"
    if stalled:
        return "stalled"
    if blocker in LOCAL_REPAIRABLE_BLOCKERS:
        return "blocked_local_repairable"
    if blocker in HUMAN_GATED_BLOCKERS:
        return "blocked_human_required"
    if verification in {"failed", "error", "failure"}:
        return "verification_failed"
    if verdict == "needs-fix":
        return "review_needs_fix"
    if verdict == "blocked":
        return "blocked_human_required"
    if verdict == "delivered":
        return "delivered_with_fixes" if _nonzero_int(fix_iterations) else "flawless"
    return "blocked_human_required"


def classify_run_quality_from_state(
    state: Dict[str, Any],
    *,
    stalled: Optional[bool] = None,
    retarget_status: Any = None,
    blocker_class: Any = None,
    completion_closeout_failed: bool = False,
) -> str:
    source_phase = state.get("current_phase")
    active = state.get("active_run")
    run_id = (active.get("run_id") if isinstance(active, dict) and active.get("phase") == source_phase
              else state.get("last_completed_run_id"))
    verification = _phase_evidence(state.get("last_verification"), source_phase, run_id)
    review = _phase_evidence(state.get("last_review"), source_phase, run_id)
    if blocker_class is None:
        blocker_class = state.get("blocker_class") or state.get("last_blocker_class")
    if stalled is None:
        stalled_count = _nonzero_int(state.get("stalled_run_count"))
        max_stalled = _nonzero_int(state.get("max_stalled_runs"))
        stalled = bool(max_stalled and stalled_count >= max_stalled)
    fix_iterations = 0
    if _normalized(review.get("verdict")) == "delivered":
        fix_iterations = max(0, _nonzero_int(review.get("iteration", state.get("review_iterations"))) - 1)
        if _normalized(verification.get("status")) not in {"passed", "pass", "success"}:
            review = {}
    return classify_run_quality(
        verification_status=verification.get("status"),
        review_verdict=review.get("verdict"),
        fix_iterations=fix_iterations,
        blocker_class=blocker_class,
        stalled=bool(stalled),
        retarget_status=retarget_status,
        completion_closeout_failed=completion_closeout_failed,
    )


def _nonzero_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value > 0:
        return value
    return 0


def _policy_object(policy: Dict[str, Any]) -> Dict[str, Any]:
    value = policy.get("adaptive_model_policy")
    if isinstance(value, dict):
        return value
    value = policy.get("adaptive")
    return value if isinstance(value, dict) else {}


def _string_list(value: Any, default: Sequence[str]) -> List[str]:
    if not isinstance(value, list):
        return list(default)
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _target_object(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _reasoning_index(value: Any) -> Optional[int]:
    text = str(value or "")
    try:
        return REASONING_ORDER.index(text)
    except ValueError:
        return None


def _next_reasoning(value: Any, max_reasoning: Any = None) -> Any:
    index = _reasoning_index(value)
    if index is None:
        return value
    cap_index = _reasoning_index(max_reasoning)
    if cap_index is None:
        cap_index = len(REASONING_ORDER) - 1
    return REASONING_ORDER[min(index + 1, cap_index)]


def _target_with_defaults(base_model: Any, base_reasoning: Any, target: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "model": target.get("model") or base_model,
        "reasoning_effort": target.get("reasoning_effort") or base_reasoning,
    }


def validate_adaptive_model_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    adaptive = _policy_object(policy)
    enabled = bool(adaptive.get("enabled")) if adaptive else False
    errors: List[Dict[str, str]] = []
    report: Dict[str, Any] = {
        "present": bool(adaptive),
        "enabled": enabled,
        "escalate_on": _string_list(adaptive.get("escalate_on"), DEFAULT_ESCALATE_ON),
        "human_gated_qualities": _string_list(adaptive.get("human_gated_qualities"), DEFAULT_HUMAN_GATED_QUALITIES),
        "deescalate_after_flawless_runs": adaptive.get("deescalate_after_flawless_runs", 0) if adaptive else 0,
        "errors": errors,
    }
    raw = policy.get("adaptive_model_policy", policy.get("adaptive", {}))
    if not isinstance(raw, dict):
        errors.append({"code": "invalid_adaptive_policy", "message": "adaptive_model_policy must be an object."})
    if not adaptive:
        return report

    for field in ("enabled",):
        if field in adaptive and not isinstance(adaptive[field], bool):
            errors.append({"code": "invalid_adaptive_policy", "message": f"adaptive_model_policy.{field} must be boolean."})

    for field in ("escalate_on", "human_gated_qualities"):
        value = adaptive.get(field)
        if value is not None and not isinstance(value, list):
            errors.append({"code": "invalid_adaptive_policy", "message": f"adaptive_model_policy.{field} must be an array."})
            continue
        for item in value or []:
            if normalize_run_quality(item) is None:
                errors.append({"code": "invalid_adaptive_run_quality", "message": f"Unknown run quality {item!r} in adaptive_model_policy.{field}."})

    deescalate_after = adaptive.get("deescalate_after_flawless_runs", 0)
    if not isinstance(deescalate_after, int) or isinstance(deescalate_after, bool) or deescalate_after < 0:
        errors.append({"code": "invalid_adaptive_policy", "message": "adaptive_model_policy.deescalate_after_flawless_runs must be a non-negative integer."})

    caps = adaptive.get("caps")
    if enabled and not isinstance(caps, dict):
        errors.append({"code": "missing_adaptive_caps", "message": "enabled adaptive_model_policy must define caps."})
        caps = {}
    elif not isinstance(caps, dict):
        caps = {}

    allowed_models = caps.get("allowed_models")
    if enabled or caps:
        if not isinstance(allowed_models, list) or not allowed_models or not all(isinstance(item, str) and item.strip() for item in allowed_models):
            errors.append({"code": "invalid_adaptive_caps", "message": "adaptive_model_policy.caps.allowed_models must be a non-empty string array."})
        max_reasoning = caps.get("max_reasoning_effort")
        if max_reasoning not in REASONING_ORDER:
            errors.append({"code": "invalid_adaptive_caps", "message": "adaptive_model_policy.caps.max_reasoning_effort must be a known reasoning effort."})

    for field in ("escalation", "deescalation", "floors"):
        target = adaptive.get(field)
        if target is not None and not isinstance(target, dict):
            errors.append({"code": "invalid_adaptive_policy", "message": f"adaptive_model_policy.{field} must be an object."})
            continue
        if not isinstance(target, dict):
            continue
        model = target.get("model")
        reasoning = target.get("min_reasoning_effort", target.get("reasoning_effort"))
        if model is not None and (not isinstance(model, str) or not model.strip()):
            errors.append({"code": "invalid_adaptive_policy", "message": f"adaptive_model_policy.{field}.model must be a non-empty string."})
        if reasoning is not None and reasoning not in REASONING_ORDER:
            errors.append({"code": "invalid_adaptive_policy", "message": f"adaptive_model_policy.{field} reasoning must be a known effort."})
        if caps and model is not None and isinstance(allowed_models, list) and model not in allowed_models:
            errors.append({"code": "adaptive_model_exceeds_caps", "message": f"adaptive_model_policy.{field}.model {model!r} is not allowed by caps.allowed_models."})
        max_reasoning = caps.get("max_reasoning_effort")
        if caps and reasoning is not None and _reasoning_index(reasoning) is not None and _reasoning_index(max_reasoning) is not None:
            if _reasoning_index(reasoning) > _reasoning_index(max_reasoning):
                errors.append({"code": "adaptive_reasoning_exceeds_caps", "message": f"adaptive_model_policy.{field} reasoning {reasoning!r} exceeds caps.max_reasoning_effort."})

    floor = _target_object(adaptive.get("floors"))
    for field in ("reasoning_effort", "min_reasoning_effort"):
        if field in floor and floor[field] not in REASONING_ORDER:
            errors.append({"code": "invalid_target_floor", "message": f"floors.{field} is unknown."})
    return report


def _propose_adaptive_action(
    policy: Dict[str, Any],
    *,
    base_model: Any,
    base_reasoning_effort: Any,
    run_quality: Any,
    flawless_streak: Any = 0,
) -> Dict[str, Any]:
    adaptive = _policy_object(policy)
    quality = normalize_run_quality(run_quality) or "blocked_human_required"
    target = {"model": base_model, "reasoning_effort": base_reasoning_effort}
    result: Dict[str, Any] = {
        "enabled": bool(adaptive.get("enabled")) if adaptive else False,
        "run_quality": quality,
        "action": "disabled",
        "target": target,
        "target_changed": False,
        "reason": "Adaptive model policy is disabled or absent.",
        "errors": [],
        "next_flawless_streak": _nonzero_int(flawless_streak),
    }
    if not result["enabled"]:
        return result

    validation = validate_adaptive_model_policy(policy)
    if validation["errors"]:
        result["action"] = "blocked_by_policy"
        result["errors"] = validation["errors"]
        result["reason"] = "Adaptive model policy is invalid."
        return result

    escalate_on = {normalize_run_quality(item) for item in _string_list(adaptive.get("escalate_on"), DEFAULT_ESCALATE_ON)}
    human_gated = {normalize_run_quality(item) for item in _string_list(adaptive.get("human_gated_qualities"), DEFAULT_HUMAN_GATED_QUALITIES)}
    caps = adaptive.get("caps") if isinstance(adaptive.get("caps"), dict) else {}

    if quality in human_gated:
        result.update(
            {
                "action": "none_human_gated",
                "reason": "Human-gated blockers require the missing human action instead of model escalation.",
                "next_flawless_streak": 0,
            }
        )
        return result

    if quality in escalate_on:
        escalation = _target_object(adaptive.get("escalation"))
        candidate = _target_with_defaults(
            base_model,
            base_reasoning_effort,
            {
                "model": escalation.get("model"),
                "reasoning_effort": escalation.get("reasoning_effort") or _next_reasoning(base_reasoning_effort, caps.get("max_reasoning_effort")),
            },
        )
        result.update(
            {
                "action": "escalate" if candidate != target else "none_at_cap",
                "target": candidate,
                "target_changed": candidate != target,
                "reason": "Run quality triggers adaptive escalation." if candidate != target else "Run quality triggers escalation, but the target is already at the configured cap.",
                "next_flawless_streak": 0,
            }
        )
        return result

    if quality == "flawless":
        next_streak = _nonzero_int(flawless_streak) + 1
        threshold = adaptive.get("deescalate_after_flawless_runs", 0)
        if isinstance(threshold, int) and not isinstance(threshold, bool) and threshold > 0 and next_streak >= threshold:
            deescalation = _target_object(adaptive.get("deescalation"))
            candidate = _target_with_defaults(base_model, base_reasoning_effort, deescalation)
            result.update(
                {
                    "action": "deescalate" if candidate != target else "none",
                    "target": candidate,
                    "target_changed": candidate != target,
                    "reason": "Flawless run streak reached the configured de-escalation threshold.",
                    "next_flawless_streak": 0 if candidate != target else next_streak,
                }
            )
            return result
        result.update(
            {
                "action": "none",
                "reason": "Flawless run keeps the current model policy target.",
                "next_flawless_streak": next_streak,
            }
        )
        return result

    result.update(
        {
            "action": "none",
            "reason": "Run quality does not trigger an adaptive model change.",
            "next_flawless_streak": 0,
        }
    )
    return result


def _phase_evidence(value: Any, phase: Any, run_id: Any = None) -> Dict[str, Any]:
    if (not isinstance(run_id, str) or not run_id.strip()
            or not isinstance(value, dict) or value.get("phase") != phase
            or value.get("run_id") != run_id):
        return {}
    return value


def quality_evidence_fingerprint(state: Dict[str, Any], phase: Any) -> str:
    active = state.get("active_run") or {}
    run_id = active.get("run_id") if active.get("phase") == phase else state.get("last_completed_run_id")
    return policy_fingerprint({
        "phase": phase,
        "verification": _phase_evidence(state.get("last_verification"), phase, run_id),
        "review": _phase_evidence(state.get("last_review"), phase, run_id),
        "blocker_class": state.get("blocker_class") or state.get("last_blocker_class"),
        "blocked_reason": state.get("blocked_reason"),
        "stalled_run_count": state.get("stalled_run_count", 0),
        "max_stalled_runs": state.get("max_stalled_runs", 2),
    })


def adaptive_provenance(policy: Dict[str, Any], state: Dict[str, Any],
                        source_phase: Any, target_phase: Any) -> Dict[str, Any]:
    active = state.get("active_run")
    run_id = (active.get("run_id") if isinstance(active, dict) and active.get("phase") == source_phase
              else state.get("last_completed_run_id"))
    source = {"current_phase": source_phase, "last_completed_run_id": run_id,
              **{key: deepcopy(state.get(key)) for key in (
                  "last_verification", "last_review", "blocker_class", "last_blocker_class",
                  "blocked_reason", "stalled_run_count", "max_stalled_runs", "review_iterations")}}
    return {"schema_version": 1, "source_phase": source_phase, "target_phase": target_phase,
            "source_run_id": run_id, "policy_version": policy.get("policy_version", policy.get("schema_version")),
            "policy_fingerprint": policy_fingerprint(policy),
            "source_evidence": source,
            "evidence_fingerprint": quality_evidence_fingerprint(source, source_phase)}


def validated_flawless_streak(state: Dict[str, Any], policy: Dict[str, Any], phase: Any) -> int:
    """Carry a streak only from a bound preceding decision for this phase."""
    action = state.get("last_adaptive_action")
    if not isinstance(action, dict):
        return 0
    proof = action.get("provenance")
    if (not isinstance(proof, dict) or proof.get("schema_version") != 1
            or not proof.get("source_run_id") or not proof.get("source_phase")
            or not proof.get("evidence_fingerprint")
            or proof.get("policy_fingerprint") != policy_fingerprint(policy)
            or proof.get("policy_version") != policy.get("policy_version", policy.get("schema_version"))
            or proof.get("target_phase") != phase or action.get("target_phase") != phase
            or action.get("run_quality") != "flawless"
            or action.get("next_flawless_streak") != state.get("adaptive_flawless_streak")
            or action.get("decision_fingerprint") != adaptive_decision_fingerprint(action)):
        return 0
    return _nonzero_int(state.get("adaptive_flawless_streak"))


def adaptive_decision_fingerprint(action: Dict[str, Any]) -> str:
    """Integrity binding, not authentication of local decision authors."""
    return policy_fingerprint({k: action.get(k) for k in (
        "action", "target", "run_quality", "provenance", "previous_flawless_streak",
        "next_flawless_streak", "capabilities_fingerprint", "host_capabilities")})


def retained_host_capabilities(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Reuse the explicit metadata bound to a decision, never infer model facts."""
    action = state.get("last_adaptive_action")
    if (isinstance(action, dict) and action.get("decision_fingerprint") == adaptive_decision_fingerprint(action)
            and isinstance(action.get("host_capabilities"), dict)
            and action.get("capabilities_fingerprint") == policy_fingerprint(action["host_capabilities"])):
        return deepcopy(action["host_capabilities"])
    return None


def resolve_adaptive_action(
    policy: Dict[str, Any], *, base_model: Any, base_reasoning_effort: Any,
    run_quality: Any, flawless_streak: Any = 0,
    host_capabilities: Optional[Dict[str, Any]] = None,
    provenance: Optional[Dict[str, Any]] = None,
    previous_action: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Propose adaptively, then enforce the same constraints on every path."""
    capabilities_fingerprint = policy_fingerprint(host_capabilities) if host_capabilities is not None else None
    if (isinstance(previous_action, dict) and isinstance(provenance, dict)
            and isinstance(provenance.get("source_run_id"), str) and provenance["source_run_id"].strip()
            and provenance.get("policy_fingerprint") == policy_fingerprint(policy)
            and previous_action.get("provenance") == provenance
            and previous_action.get("target_phase") == provenance.get("target_phase")
            and previous_action.get("run_quality") == normalize_run_quality(run_quality)
            and previous_action.get("capabilities_fingerprint") == capabilities_fingerprint
            and previous_action.get("decision_fingerprint") == adaptive_decision_fingerprint(previous_action)):
        # State may already contain this decision's output after an interrupted retarget.
        flawless_streak = previous_action.get("previous_flawless_streak", 0)
    result = _propose_adaptive_action(policy, base_model=base_model,
        base_reasoning_effort=base_reasoning_effort, run_quality=run_quality,
        flawless_streak=flawless_streak)
    validation = validate_adaptive_model_policy(policy)
    resolution = resolve_model_target(policy,
        base_target={"model": base_model, "reasoning_effort": base_reasoning_effort},
        proposal=result["target"], host_capabilities=host_capabilities)
    result["errors"] = validation["errors"] + resolution["errors"]
    if normalize_run_quality(run_quality) is None:
        result["errors"].append({"code": "invalid_run_quality", "message": "Run quality is unknown."})
    result["resolution"] = resolution
    result["provenance"] = provenance
    result["previous_flawless_streak"] = _nonzero_int(flawless_streak)
    result["capabilities_fingerprint"] = capabilities_fingerprint
    result["host_capabilities"] = deepcopy(host_capabilities)
    if result["errors"]:
        result.update(action="blocked_by_policy", target=None, target_changed=False,
                      reason="Adaptive target cannot satisfy the current policy constraints.")
    else:
        result["target"] = resolution["target"]
        result["target_changed"] = result["target"] != {"model": base_model, "reasoning_effort": base_reasoning_effort}
        if result["action"] == "deescalate" and not result["target_changed"]:
            result["action"] = "none_at_floor"
        if resolution["adjustments"]:
            result["reason"] += " Applied constraints: " + ", ".join(resolution["adjustments"]) + "."
    result["decision_fingerprint"] = adaptive_decision_fingerprint(result)
    return result


def persisted_adaptive_target(state: Dict[str, Any], current_phase: Any,
                              policy: Dict[str, Any], *,
                              host_capabilities: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Only bound decisions can override the current phase's base requirement."""
    action = state.get("last_adaptive_action")
    result = {"status": "absent", "target": None, "errors": []}
    if not isinstance(action, dict):
        return result
    adaptive = _policy_object(policy)
    provenance = action.get("provenance")
    if not adaptive.get("enabled"):
        return {**result, "status": "ignored_disabled"}
    if not isinstance(provenance, dict):
        return {**result, "status": "ignored_unbound"}
    if action.get("decision_fingerprint") != adaptive_decision_fingerprint(action):
        return {**result, "status": "ignored_changed_decision"}
    if host_capabilities is None:
        host_capabilities = retained_host_capabilities(state)
    capabilities_fingerprint = policy_fingerprint(host_capabilities) if host_capabilities is not None else None
    if action.get("capabilities_fingerprint") != capabilities_fingerprint:
        return {**result, "status": "ignored_changed_capabilities"}
    source_phase = provenance.get("source_phase")
    source_state = provenance.get("source_evidence")
    if not isinstance(source_state, dict):
        return {**result, "status": "ignored_unbound"}
    expected = adaptive_provenance(policy, source_state, source_phase, current_phase)
    if (not source_phase or not expected["source_run_id"] or provenance != expected
            or action.get("target_phase") != current_phase):
        return {**result, "status": "ignored_stale"}
    # Source evidence, rather than the cached scalar, determines quality.
    # New destination-phase evidence must not invalidate the source decision.
    # Corrections to the same source run do invalidate its retained snapshot.
    for field in ("last_review", "last_verification"):
        live = state.get(field)
        if (isinstance(live, dict) and live.get("phase") == source_phase
                and live.get("run_id") == provenance["source_run_id"]
                and live != source_state.get(field)):
            return {**result, "status": "ignored_stale"}
    quality = classify_run_quality_from_state(source_state)
    if action.get("run_quality") != quality:
        return {**result, "status": "ignored_stale_quality"}
    target = action.get("target")
    if not isinstance(target, dict):
        return {**result, "status": "invalid_policy", "errors": [
            {"code": "invalid_persisted_target", "message": "Bound adaptive target must be an object."}]}
    base = resolve_phase_target(policy, current_phase)
    resolution = resolve_model_target(policy, base_target=base, proposal=target,
                                      host_capabilities=host_capabilities)
    return {**resolution, "source": "state.last_adaptive_action",
            "reason": action.get("reason") or "Bound adaptive decision validated against current policy."}


def adaptive_target_from_state(state: Dict[str, Any], current_phase: Any,
                               policy: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    # Legacy reporting callers without the current policy cannot confer authority.
    if policy is None:
        return None
    result = persisted_adaptive_target(state, current_phase, policy)
    if result["status"] != "resolved":
        return None
    return {**result["target"], "source": result["source"], "reason": result["reason"]}
