"""Policy normalization helpers shared by inspection and validation."""

from __future__ import annotations

import re
import hashlib
import json
from typing import Any, Optional


REASONING_ORDER = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
ALLOWED_REASONING_EFFORTS = set(REASONING_ORDER)


def policy_fingerprint(policy: dict[str, Any]) -> str:
    """Bind decisions to all policy values, including unversioned edits."""
    raw = json.dumps(policy, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resolve_phase_target(policy: dict[str, Any], phase: Any) -> dict[str, Any]:
    """Resolve explicit overrides without treating malformed values as missing."""
    defaults = policy.get("defaults", {})
    phases = policy.get("phases", {})
    key = phase_number(phase) or str(phase)
    override = phases.get(key, {}) if isinstance(phases, dict) else None
    if not isinstance(defaults, dict) or not isinstance(override, dict):
        return {"model": None, "reasoning_effort": None, "source": "invalid_policy"}
    return {
        "model": override.get("model", defaults.get("model")),
        "reasoning_effort": override.get("reasoning_effort", defaults.get("reasoning_effort")),
        "source": f"phases.{key}" if isinstance(phases, dict) and key in phases else "defaults",
        "phase_policy_found": isinstance(phases, dict) and key in phases,
    }


def _trusted_capabilities(metadata: Any) -> bool:
    return bool(isinstance(metadata, dict) and metadata.get("trusted") is True
                and isinstance(metadata.get("source"), str) and metadata["source"].strip()
                and isinstance(metadata.get("models"), dict))


def configured_host_support(model: Any, reasoning: Any,
                            host_capabilities: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Check observed values exactly; a supported alternative is not readback."""
    if not _trusted_capabilities(host_capabilities) or model is None or reasoning is None:
        return {"status": "unknown", "errors": []}
    entry = host_capabilities["models"].get(model) if isinstance(model, str) else None
    efforts = entry.get("reasoning_efforts") if isinstance(entry, dict) else None
    if (isinstance(efforts, list) and efforts and all(value in REASONING_ORDER for value in efforts)
            and reasoning in efforts):
        return {"status": "supported", "errors": []}
    return {"status": "unsupported", "errors": [{"code": "configured_target_host_unsupported",
            "message": f"Configured model/reasoning {model!r}/{reasoning!r} is not supported by trusted host capabilities."}]}


def resolve_model_target(
    policy: dict[str, Any], *, base_target: dict[str, Any],
    proposal: Optional[dict[str, Any]] = None,
    host_capabilities: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Resolve requirements, proposal and constraints without effects or guesses.

    Capability metadata is supplied explicitly by a trusted adapter/operator;
    self-declared provider/cost fields in a proposal confer no authority.
    Unknown host support is reported, and explicit metadata limits fail closed.
    """
    errors = []
    adjustments = []

    def fail(code: str, message: str) -> None:
        errors.append({"code": code, "message": message})

    adaptive = policy.get("adaptive_model_policy", policy.get("adaptive", {}))
    if not isinstance(adaptive, dict):
        fail("invalid_adaptive_policy", "adaptive_model_policy must be an object.")
        adaptive = {}
    if "enabled" in adaptive and not isinstance(adaptive["enabled"], bool):
        fail("invalid_adaptive_policy", "Adaptive enabled must be boolean.")
    caps = adaptive.get("caps", {})
    floors = adaptive.get("floors", {})
    if not isinstance(caps, dict) or not isinstance(floors, dict):
        fail("invalid_target_constraints", "floors and caps must be objects.")
        caps, floors = {}, {}
    if adaptive.get("enabled") is True and (not caps.get("allowed_models") or not caps.get("max_reasoning_effort")):
        fail("missing_adaptive_caps", "Enabled adaptation requires an explicit model allowlist and reasoning cap.")
    candidate = {k: (proposal[k] if proposal is not None and k in proposal else base_target.get(k))
                 for k in ("model", "reasoning_effort")}
    for label, target in (("base", base_target), ("proposal", candidate)):
        model = target.get("model")
        effort = target.get("reasoning_effort")
        if not isinstance(model, str) or not model.strip() or model != model.strip():
            fail("invalid_target_model", f"{label} model must be a non-empty unpadded string.")
        if effort not in REASONING_ORDER:
            fail("invalid_target_reasoning", f"{label} reasoning effort is unknown.")
        allowed = caps.get("allowed_models")
        if allowed is not None:
            if not isinstance(allowed, list) or not allowed or any(not isinstance(m, str) or not m.strip() for m in allowed):
                fail("invalid_adaptive_caps", "allowed_models must be a non-empty string array.")
            elif model not in allowed:
                fail("target_model_exceeds_caps", f"{label} model {model!r} is outside allowed_models.")
    base_effort = base_target.get("reasoning_effort")
    minimums = [floors[k] for k in ("min_reasoning_effort", "reasoning_effort") if k in floors]
    if any(x not in REASONING_ORDER for x in minimums):
        fail("invalid_target_floor", "Reasoning floor is unknown.")
    floor_rank = max((REASONING_ORDER.index(x) for x in [base_effort, *minimums] if x in REASONING_ORDER), default=0)
    cap = caps.get("max_reasoning_effort")
    if cap is not None and cap not in REASONING_ORDER:
        fail("invalid_adaptive_caps", "Reasoning cap is unknown.")
    cap_rank = REASONING_ORDER.index(cap) if cap in REASONING_ORDER else len(REASONING_ORDER) - 1
    if floor_rank > cap_rank:
        fail("target_floor_above_cap", "Applicable reasoning floor exceeds the cap.")
    if candidate["reasoning_effort"] in REASONING_ORDER:
        rank = REASONING_ORDER.index(candidate["reasoning_effort"])
        if rank > cap_rank:
            fail("target_reasoning_exceeds_caps", "Proposed reasoning exceeds the cap.")
        elif rank < floor_rank:
            candidate["reasoning_effort"] = REASONING_ORDER[floor_rank]
            adjustments.append("reasoning_raised_to_floor")

    metadata = host_capabilities
    trusted = _trusted_capabilities(metadata)
    support = "unknown"
    limits = {}
    for field, attribute in (("allowed_providers", "provider"), ("allowed_cost_classes", "cost_class")):
        allowed = caps.get(field)
        if allowed is None:
            limits[field] = "not_requested"
            continue
        limits[field] = "unresolved"
        if not isinstance(allowed, list) or not allowed or any(not isinstance(v, str) or not v.strip() for v in allowed):
            fail("invalid_adaptive_caps", f"{field} must be a non-empty string array.")
            continue
        entry = metadata["models"].get(candidate["model"], {}) if trusted and isinstance(candidate["model"], str) else {}
        value = entry.get(attribute) if isinstance(entry, dict) else None
        if not isinstance(value, str) or not value.strip():
            fail("target_metadata_unavailable", f"Trusted {attribute} metadata is required to enforce {field}.")
        elif value not in allowed:
            limits[field] = "rejected"
            fail("target_metadata_exceeds_caps", f"Target {attribute} {value!r} is outside {field}.")
        else:
            limits[field] = "enforced"
    if trusted:
        entry = metadata["models"].get(candidate["model"]) if isinstance(candidate["model"], str) else None
        efforts = entry.get("reasoning_efforts") if isinstance(entry, dict) else None
        support = "unsupported"
        if not isinstance(efforts, list) or not efforts or any(x not in REASONING_ORDER for x in efforts):
            fail("target_host_unsupported", "Target model lacks valid explicit host reasoning capabilities.")
        elif candidate["reasoning_effort"] not in efforts:
            # Select the least supported value that meets the requirement/cap.
            rank = REASONING_ORDER.index(candidate["reasoning_effort"]) if candidate["reasoning_effort"] in REASONING_ORDER else len(REASONING_ORDER)
            choices = [x for x in REASONING_ORDER if x in efforts and rank <= REASONING_ORDER.index(x) <= cap_rank]
            if choices:
                candidate["reasoning_effort"] = choices[0]
                adjustments.append("reasoning_raised_to_supported_value")
                support = "supported"
            else:
                fail("target_host_unsupported", "No supported reasoning value satisfies the floor and cap.")
        else:
            support = "supported"
    model_floor = floors.get("model")
    if model_floor is not None:
        models = metadata["models"] if trusted else {}
        lower = models.get(model_floor, {}) if isinstance(model_floor, str) else {}
        selected = models.get(candidate["model"], {}) if isinstance(candidate["model"], str) else {}
        lower_rank = lower.get("rank") if isinstance(lower, dict) else None
        selected_rank = selected.get("rank") if isinstance(selected, dict) else None
        if type(lower_rank) is not int or type(selected_rank) is not int:
            fail("target_metadata_unavailable", "A model floor requires explicit trusted model ranks.")
        elif selected_rank < lower_rank:
            fail("target_model_below_floor", "Target model is below the explicit model floor.")
    return {"status": "invalid_policy" if errors else "resolved", "target": None if errors else candidate,
            "errors": errors, "adjustments": adjustments, "host_support": support,
            "metadata_limits": limits, "reasoning_floor": REASONING_ORDER[floor_rank],
            "reasoning_cap": cap, "policy_fingerprint": policy_fingerprint(policy)}
COMPLETED_STATUSES = {
    "complete",
    "completed",
    "delivered",
    "completed-pending-pause",
    "completed_pending_pause",
    "all-phases-complete",
    "all_phases_complete",
}
ACTIVE_STATUSES = {
    "in progress",
    "in-progress",
    "active",
    "delivering",
    "verifying",
    "reviewing",
    "fixing",
    "blocked",
}


def normalized(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def reasoning_effort_rank(value: Any) -> Optional[int]:
    text = normalized(value)
    try:
        return REASONING_ORDER.index(text)
    except ValueError:
        return None


def reasoning_effort_satisfies(configured: Any, required: Any) -> bool:
    """Return true when configured reasoning is at least the required floor."""

    configured_rank = reasoning_effort_rank(configured)
    required_rank = reasoning_effort_rank(required)
    if configured_rank is None or required_rank is None:
        return False
    return configured_rank >= required_rank


def reasoning_effort_exceeds(configured: Any, required: Any) -> bool:
    configured_rank = reasoning_effort_rank(configured)
    required_rank = reasoning_effort_rank(required)
    if configured_rank is None or required_rank is None:
        return False
    return configured_rank > required_rank


def phase_number(value: Any) -> Optional[str]:
    match = re.search(r"\bPhase\s+(\d+)\b", str(value or ""), re.IGNORECASE)
    return match.group(1) if match else None


def has_hard_stop_guard(prompt: str) -> bool:
    lowered = prompt.lower()
    complete_marker = "completed_pending_pause" in lowered or "all_phases_complete" in lowered
    stop_marker = "do not start" in lowered or "hard-stop" in lowered or "hard stop" in lowered
    return complete_marker and stop_marker


def has_blocked_remediation_guard(prompt: str) -> bool:
    lowered = prompt.lower()
    blocked_marker = "status: blocked" in lowered or "status is `blocked`" in lowered or "status is blocked" in lowered
    remediation_marker = "blocked remediation" in lowered or "blocker remediation" in lowered
    repair_marker = "repair" in lowered and "advance" in lowered
    return blocked_marker and remediation_marker and repair_marker


def has_state_resolved_roadmap_guard(prompt: str) -> bool:
    """Return true when the prompt treats delivery_state.json as roadmap source."""

    lowered = " ".join(str(prompt or "").lower().split())
    if "delivery_state.json" not in lowered:
        return False
    if "automation_guide.md" in lowered or "delivery_log.md" in lowered:
        return True
    markers = (
        "resolve the current roadmap path from delivery_state.json",
        "resolve roadmap path from delivery_state.json",
        "roadmap path from delivery_state.json",
        "roadmap path recorded in delivery_state.json",
        "roadmap field in delivery_state.json is authoritative",
        "state roadmap field is authoritative",
        "delivery_state.json is the source of truth for the roadmap path",
    )
    return any(marker in lowered for marker in markers)


def paused_active_status_drift(reason: Any) -> bool:
    text = normalized(reason)
    return "paused" in text and "active" in text and (
        "automation" in text or "runner" in text or "saved" in text or "status" in text
    )


def manual_activation_reconciliation(
    state: Optional[dict[str, Any]],
    automation_status: Any,
    model_policy: Optional[dict[str, Any]],
    *,
    blocked_remediation_guard: bool,
    hard_stop_guard: bool,
    complete: bool,
) -> dict[str, Any]:
    blocked_reason = state.get("blocked_reason") if state else None
    model_mismatch = bool(model_policy and model_policy.get("model_mismatch"))
    reasoning_mismatch = bool(model_policy and model_policy.get("reasoning_mismatch"))
    model_unknown = bool(model_policy and model_policy.get("model_unknown"))
    reasoning_unknown = bool(model_policy and model_policy.get("reasoning_unknown"))
    model_policy_clean = not (model_mismatch or reasoning_mismatch or model_unknown or reasoning_unknown)
    active_readback = str(automation_status or "").upper() == "ACTIVE"
    blocked_state = normalized(state.get("status") if state else None) == "blocked"
    paused_active_drift = paused_active_status_drift(blocked_reason)
    available = (
        blocked_state
        and active_readback
        and paused_active_drift
        and model_policy_clean
        and blocked_remediation_guard
        and hard_stop_guard
        and not complete
    )
    return {
        "available": available,
        "classification": "automation-config" if paused_active_drift else None,
        "blocked_reason_indicates_paused_active_drift": paused_active_drift,
        "active_readback": active_readback,
        "blocked_state": blocked_state,
        "model_policy_clean": model_policy_clean,
        "blocked_remediation_guard": blocked_remediation_guard,
        "hard_stop_guard": hard_stop_guard,
        "complete": complete,
        "recommended_action": (
            "Record manual/operator activation acceptance, update durable status surfaces to ACTIVE, "
            "clear blocked_reason after validation, reset stalled counters, and resume the current phase."
            if available
            else None
        ),
    }
