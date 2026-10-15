"""Versioned, inspectable saved-prompt upgrades with narrow host effects."""
from __future__ import annotations

from copy import deepcopy
import difflib
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, Optional, Protocol

from . import __version__
from .approval import validate_approval_policy
from .automation import RunnerError, config_revision, validate_runner_snapshot, utc_now
from .state import load_json_object, write_json_object

VERSIONS = {"framework": __version__, "prompt_template": 3, "policy": 2, "progress_evidence": 1}
IDENTITY_KEYS = ("id", "cwds", "target", "execution_environment")


class MigrationAdapter(Protocol):
    """Supported host transport, never an implicit live file editor.

    update_prompt_only must CAS expected_revision, preserve all other settings,
    and make request_id idempotent. Readback must be scheduler-authoritative.
    """
    def readback(self, automation_id: str) -> Dict[str, Any]: ...
    def update_prompt_only(self, request: Dict[str, Any]) -> None: ...


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def version_record(source: str, **provenance: Any) -> Dict[str, Any]:
    return {"schema_version": 1, "versions": deepcopy(VERSIONS),
            "provenance": {"source": source, **provenance}}


def render_prompt(slug: str, template: Optional[str] = None, *, roadmap: Optional[str] = None) -> str:
    if not isinstance(slug, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", slug):
        raise ValueError("Migration requires a safe, concrete roadmap slug.")
    text = CURRENT_PROMPT if template is None else template
    return text.replace("<roadmap-slug>", slug).replace("ROADMAP_PATH", roadmap or "ROADMAP_PATH")


def _settings(config: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in config.items() if key not in {"prompt", "updated_at"}}


def _binding(plan: Dict[str, Any]) -> Dict[str, Any]:
    return {key: plan[key] for key in ("schema_version", "versions", "expected", "slug", "roadmap",
                                      "before", "after", "before_policy", "after_policy", "policy_path", "provenance",
                                      "observed_revision", "observed_source", "supersedes_rollback")}


def plan_migration(snapshot: Dict[str, Any], expected: Dict[str, Any], slug: str,
                   policy: Any, *, roadmap: Optional[str] = None, policy_path: Optional[str] = None,
                   supersedes_rollback: Optional[str] = None) -> Dict[str, Any]:
    """Read-only plan. Exact provenance recognition never grants update authority."""
    config = validate_runner_snapshot(snapshot, expected)
    if supersedes_rollback is not None and not re.fullmatch(r"[0-9a-f]{64}", supersedes_rollback):
        raise ValueError("supersedes_rollback must be the digest of a verified rollback receipt.")
    if not all(key in expected and key in config for key in IDENTITY_KEYS):
        raise RunnerError("identity_mismatch", "Migration requires id, cwd, project target and execution scope.")
    target = render_prompt(slug)
    prompt = config.get("prompt")
    known = next((rev for rev, text in LEGACY_PROMPTS.items()
                  if prompt == render_prompt(slug, text, roadmap=roadmap)), None)
    issues = []
    if not isinstance(prompt, str) or (known is None and prompt != target):
        issues.append("unknown_prompt_provenance")
    if policy is None:
        issues.append("missing_policy")
    elif not isinstance(policy, dict) or validate_approval_policy(policy):
        issues.append("invalid_policy")
    after_policy = deepcopy(policy)
    # Missing context flags already mean default safety pause in the runtime.
    # Make that default explicit only for the exact known generated policy.
    from .approval import default_approval_policy
    generated = default_approval_policy("conservative")
    legacy_policy = {k: v for k, v in generated.items() if not k.startswith("pause_automation_on_")}
    policy_known = policy in (generated, legacy_policy)
    if isinstance(policy, dict) and not issues:
        if policy == legacy_policy:
            after_policy = generated
        # Custom policies and explicit false values are preserved byte-for-value.
    after = deepcopy(config)
    if not issues:
        after["prompt"] = target
    plan = {"schema_version": 1, "versions": deepcopy(VERSIONS), "expected": deepcopy(expected),
            "slug": slug, "roadmap": roadmap, "before": deepcopy(config), "after": after,
            "before_policy": deepcopy(policy), "after_policy": after_policy,
            "policy_path": str(Path(policy_path).resolve()) if policy_path else None,
            "supersedes_rollback": supersedes_rollback,
            "provenance": {"prompt_source": known or ("current_template" if prompt == target else "unknown"),
                           "policy_source": "generated_default" if policy_known else "operator_custom"},
            "observed_revision": snapshot["revision"], "observed_source": snapshot["source"],
            "detected": bool(known or issues or after_policy != policy), "issues": issues,
            "status": "needs-decision" if issues else ("planned" if after != config or after_policy != policy else "verified"),
            "effects": [], "diffs": {}, "configured_readback": deepcopy(config)}
    plan["plan_id"] = digest(_binding(plan))
    for label, before, after_value in (("prompt", prompt, after.get("prompt")), ("policy", policy, after_policy)):
        a = before if isinstance(before, str) else json.dumps(before, indent=2, sort_keys=True)
        b = after_value if isinstance(after_value, str) else json.dumps(after_value, indent=2, sort_keys=True)
        plan["diffs"][label] = "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True),
                                                         fromfile="before/"+label, tofile="after/"+label))
        if before != after_value:
            plan["effects"].append("update_prompt_only" if label == "prompt" else "write_policy")
    plan["required_action"] = ("Resolve " + ", ".join(issues) + "; no automatic rewrite." if issues
                               else "Authorize this exact plan and its listed effects." if plan["effects"] else None)
    return plan


def validate_plan(plan: Dict[str, Any]) -> None:
    try:
        if plan.get("plan_id") != digest(_binding(plan)):
            raise ValueError("Plan content changed.")
        from .automation import runner_snapshot
        rebuilt = plan_migration(runner_snapshot(plan["before"], source=plan["observed_source"], revision=plan["observed_revision"]),
                                 plan["expected"], plan["slug"], plan["before_policy"], roadmap=plan["roadmap"],
                                 policy_path=plan["policy_path"], supersedes_rollback=plan["supersedes_rollback"])
        if _binding(rebuilt) != _binding(plan) or rebuilt["effects"] != plan.get("effects") or rebuilt["issues"]:
            raise ValueError("Unrecognized migration or altered effects.")
    except (KeyError, TypeError, ValueError, RunnerError) as exc:
        raise RunnerError("invalid_plan", str(exc)) from exc


def remember_decision(path: Path, plan: Dict[str, Any], *, decision: str = "pending", source: Optional[str] = None) -> Dict[str, Any]:
    """Persist once per exact decision; callers own repository-write authorization."""
    if decision not in {"pending", "declined", "approved"} or (decision != "pending" and not source):
        raise ValueError("An explicit operator decision requires its source.")
    old = load_json_object(path) if path.exists() else {}
    decisions = old.setdefault("decisions", {})
    # Transport revisions/timestamps do not make an unchanged operator question
    # new. Authorization still binds the exact plan_id, never this display key.
    question = _binding(plan)
    question.pop("observed_revision"); question.pop("observed_source")
    for key in ("before", "after"):
        question[key] = {k:v for k,v in question[key].items() if k != "updated_at"}
    decision_id = digest({**question, "issues": plan["issues"], "effects": plan["effects"]})
    existing = decisions.get(decision_id)
    if existing and decision == "pending":
        return {**existing, "ask_again": False}
    item = {"plan_id": plan["plan_id"], "decision_id": decision_id, "runner_id": plan["expected"]["id"], "decision": decision,
            "effects": plan["effects"], "issues": plan["issues"], "source": source,
            "required_action": plan["required_action"], "recorded_at": utc_now()}
    decisions[decision_id] = item
    write_json_object(path, old)
    return {**item, "ask_again": decision == "pending"}


def _authorized(authority: Any, plan: Dict[str, Any], direction: str) -> bool:
    return bool(isinstance(authority, dict) and authority.get("authorized") is True
                and authority.get("runner_id") == plan["expected"]["id"]
                and authority.get("plan_id") == plan["plan_id"]
                and authority.get("direction") == direction and authority.get("source")
                and authority.get("effects") == plan["effects"])


def _historical_receipt(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    receipt = entry.get("receipt")
    if (isinstance(receipt, dict) and receipt.get("scheduler_authoritative") is True
            and receipt.get("plan_id") == entry.get("plan_id")
            and receipt.get("direction") == entry.get("direction")
            and receipt.get("source") and receipt.get("observed_revision")):
        return receipt
    return None


def rollback_plan(plan: Dict[str, Any], snapshot: Dict[str, Any], policy: Any) -> Dict[str, Any]:
    """Revert only owned values still equal to the migrated values.

    Subsequent non-prompt settings are preserved from fresh readback; changed
    prompt/policy needs a human decision. No whole-runner snapshot restore.
    """
    validate_plan(plan)
    current = validate_runner_snapshot(snapshot, plan["expected"])
    conflicts = []
    if current.get("prompt") != plan["after"].get("prompt"):
        conflicts.append("prompt_changed_after_migration")
    if "write_policy" in plan["effects"] and policy != plan["after_policy"]:
        conflicts.append("policy_changed_after_migration")
    payload = {**current, "prompt": plan["before"]["prompt"]}
    return {"status": "needs-decision" if conflicts else "planned", "issues": conflicts,
            "plan_id": plan["plan_id"], "direction": "rollback", "expected_revision": snapshot["revision"],
            "payload": payload, "policy": deepcopy(plan["before_policy"])}


def resume_migration(plan: Dict[str, Any], journal_path: Path, *, adapter: MigrationAdapter,
                     authority: Any = None, policy_path: Optional[Path] = None,
                     direction: str = "forward", max_attempts: int = 3) -> Dict[str, Any]:
    """Write intent before effects, then require fresh exact readback.

    Local journal locks serialize cooperative writers. Host CAS rejects races.
    Interrupted post-effect runs verify first, without repeating the effect.
    Authority is supplied by trusted setup/session evidence, not the plan.
    """
    validate_plan(plan)
    if direction not in {"forward", "rollback"} or type(max_attempts) is not int or not 1 <= max_attempts <= 3:
        raise ValueError("Direction and bounded retry count required.")
    from .progress import _recording_lock
    with _recording_lock(journal_path):
        journal = load_json_object(journal_path) if journal_path.exists() else {"schema_version": 1, "entries": {}}
        key = plan["plan_id"] + ":" + direction
        entry = journal["entries"].get(key, {"plan_id": plan["plan_id"], "direction": direction,
                                                "status": "planned", "attempts": 0, "max_attempts": max_attempts,
                                                "effects_applied": [], "receipt": None})
        entry.setdefault("max_attempts", max_attempts)
        entry.setdefault("effects_applied", [])
        last_saved = deepcopy(journal["entries"].get(key))
        def save(status: str, action: Optional[str] = None) -> Dict[str, Any]:
            nonlocal last_saved
            repeated = (entry.get("status") == status and entry.get("required_action") == action
                        and last_saved == entry)
            if repeated:
                return {**deepcopy(entry), "ask_again": False}
            entry.update(status=status, required_action=action)
            journal["entries"][key] = entry
            write_json_object(journal_path, journal)
            last_saved = deepcopy(entry)
            return {**deepcopy(entry), "ask_again": status == "needs-decision"}
        if plan["effects"] and not _authorized(authority, plan, direction):
            return save("needs-decision", "Provide scoped operator authorization for this exact plan, direction and effects.")
        entry["authority"] = deepcopy(authority)
        # A failed recheck changes attempt status, never historical verification.
        rollbacks = {digest(receipt): receipt for item in journal["entries"].values()
                     if (receipt := _historical_receipt(item)) is not None
                     and receipt["direction"] == "rollback"}
        predecessors = {key for key, receipt in rollbacks.items()
                        if receipt["plan_id"] != plan["plan_id"]
                        and receipt.get("runner_id") == plan["expected"]["id"]
                        and receipt.get("policy_path", plan["policy_path"]) == plan["policy_path"]
                        and receipt.get("prompt_digest") == digest(plan["before"]["prompt"])
                        and receipt.get("policy_digest") == digest(plan["before_policy"])}
        if plan["supersedes_rollback"] and plan["supersedes_rollback"] not in predecessors:
            return save("needs-decision", "Referenced verified rollback receipt does not match this migration's runner and starting values.")
        if any(rollbacks.get(prior, {}).get("plan_id") == plan["plan_id"]
               for item in journal["entries"].values()
               for prior in item.get("supersedes_rollbacks", [])):
            return save("needs-decision", "This transaction was superseded; inspect the newer migration instead of reusing historical authority.")
        if direction == "forward" and plan["effects"] and any(
                receipt["plan_id"] == plan["plan_id"] for receipt in rollbacks.values()):
            return save("needs-decision", "This exact plan was rolled back; inspect fresh readback and authorize a new plan.")
        try:
            snapshot = adapter.readback(plan["expected"]["id"])
            current = validate_runner_snapshot(snapshot, plan["expected"])
            start, target = (plan["before"], plan["after"]) if direction == "forward" else (plan["after"], plan["before"])
            policy_start, policy_target = (plan["before_policy"], plan["after_policy"]) if direction == "forward" else (plan["after_policy"], plan["before_policy"])
            policy_owned = "write_policy" in plan["effects"]
            if policy_owned and policy_path is not None and policy_path.is_symlink():
                return save("needs-decision", "Policy writes cannot replace a symlink; select its exact approved regular file.")
            if (plan.get("policy_path") and (policy_path is None or str(policy_path.resolve()) != plan["policy_path"])):
                return save("needs-decision", "Policy path differs from the authorized migration plan.")
            if not plan.get("policy_path"):
                return save("needs-decision", "Bind the exact policy file path before authorizing or verifying any migration.")
            policy_current = load_json_object(policy_path) if policy_path is not None else None
            if policy_path is None:
                return save("needs-decision", "Read back the existing policy path before applying this plan.")
            if not policy_owned and policy_current != plan["before_policy"]:
                return save("needs-decision", "Policy changed; rebuild the plan without overriding operator restrictions.")
            if policy_owned and (policy_path is None or policy_current not in (policy_start, policy_target)):
                return save("needs-decision", "Policy missing or concurrently changed; reconcile it before migration.")
            if direction == "forward" and _settings(current) != _settings(plan["before"]):
                return save("needs-decision", "Runner settings changed; rebuild and authorize a fresh plan.")
            if current.get("prompt") not in (start.get("prompt"), target.get("prompt")):
                return save("needs-decision", "Prompt changed; preserve the operator edit and replan.")
            needs_prompt = current.get("prompt") != target.get("prompt")
            needs_policy = policy_owned and policy_current != policy_target
            if (needs_prompt or needs_policy) and _historical_receipt(entry) is not None:
                return save("needs-decision", "Previously verified values changed; authorize a new transaction instead of repeating this completed effect.")
            def begin_effect() -> bool:
                if entry["attempts"] >= min(max_attempts, entry["max_attempts"]):
                    return False
                entry["attempts"] += 1
                if direction == "forward":
                    entry["supersedes_rollbacks"] = sorted(set(entry.get("supersedes_rollbacks", [])) | predecessors)
                save("applied" if entry["effects_applied"] else "planned")
                return True
            if needs_prompt:
                if entry["attempts"] >= min(max_attempts, entry["max_attempts"]):
                    return save("needs-decision", "Migration retry bound reached; inspect runner readback.")
                if not callable(getattr(adapter, "update_prompt_only", None)):
                    return save("needs-decision", "Host has no supported prompt update capability.")
                payload = {**current, "prompt": target["prompt"]}
                request = {"schema_version": 1, "operation": "update_prompt_only", "runner_id": current["id"],
                           "request_id": key, "expected_revision": snapshot["revision"], "payload": payload,
                           "settings_sha256": config_revision(_settings(current)), "plan_id": plan["plan_id"]}
                entry.update(request=request, before_digest=digest(start), after_digest=digest(target))
                begin_effect()
                adapter.update_prompt_only(request)
                if "update_prompt_only" not in entry["effects_applied"]:
                    entry["effects_applied"].append("update_prompt_only")
                save("applied")
                snapshot = adapter.readback(current["id"])
                observed = validate_runner_snapshot(snapshot, plan["expected"])
                if _settings(observed) != _settings(current) or observed.get("prompt") != target["prompt"]:
                    return save("applied", "Prompt update is unconfirmed or unrelated settings changed; inspect readback.")
                current = observed
            if needs_policy:
                # Recheck immediately before replacement; cooperating local writers
                # share this directory lock. Never repair unrelated local policies.
                if load_json_object(policy_path) != policy_start:
                    return save("needs-decision", "Policy changed before replacement; preserve it.")
                if not begin_effect():
                    return save("needs-decision", "Migration retry bound reached; inspect policy and runner readback.")
                write_json_object(policy_path, policy_target)
                if "write_policy" not in entry["effects_applied"]:
                    entry["effects_applied"].append("write_policy")
                save("applied")
                if load_json_object(policy_path) != policy_target:
                    return save("applied", "Policy readback failed.")
            # Policies can be edited while the host effect is in flight. Verify
            # all policy values again, including policies this plan never owns.
            if load_json_object(policy_path) != policy_target:
                return save("needs-decision", "Policy changed during host update; preserve the edit and reconcile the partial migration.")
            final_snapshot = adapter.readback(current["id"])
            final_config = validate_runner_snapshot(final_snapshot, plan["expected"])
            if _settings(final_config) != _settings(current) or final_config.get("prompt") != target["prompt"]:
                return save("needs-decision", "Runner changed during migration closeout; preserve the edit and reconcile readback.")
            snapshot, current = final_snapshot, final_config
            if _historical_receipt(entry) is not None:
                return save("verified")
            entry["receipt"] = {"runner_id": current["id"], "plan_id": plan["plan_id"], "direction": direction,
                                "before_digest": digest(start), "after_digest": digest(current),
                                "prompt_digest": digest(current["prompt"]), "policy_digest": digest(policy_target),
                                "policy_path": plan["policy_path"],
                                "observed_revision": snapshot["revision"], "source": snapshot["source"],
                                "scheduler_authoritative": True, "verified_at": utc_now(),
                                "versions": deepcopy(VERSIONS) if direction == "forward" else None}
            return save("verified")
        except (RunnerError, OSError, RuntimeError, ValueError) as exc:
            if isinstance(exc, RunnerError) and not exc.transient:
                return save("needs-decision", str(exc))
            return save("applied" if entry.get("status") == "applied" else "planned", str(exc))


def record_verified_migration(state: Dict[str, Any], plan: Dict[str, Any], outcome: Dict[str, Any]) -> Dict[str, Any]:
    """Merge receipt/version provenance without inventing configured runner fields.

    The host adapter supplies the outcome; the caller writes the resulting state
    under the ordinary repository-local state lock. Existing history is retained.
    """
    validate_plan(plan)
    receipt = outcome.get("receipt")
    if (outcome.get("status") != "verified" or not isinstance(receipt, dict)
            or receipt.get("scheduler_authoritative") is not True
            or receipt.get("plan_id") != plan["plan_id"]
            or receipt.get("runner_id") != plan["expected"]["id"]
            or receipt.get("direction") not in {"forward", "rollback"}
            or receipt.get("prompt_digest") != digest(plan["after" if receipt["direction"] == "forward" else "before"]["prompt"])
            or receipt.get("policy_digest") != digest(plan["after_policy" if receipt["direction"] == "forward" else "before_policy"])
            or not receipt.get("source") or not receipt.get("observed_revision")):
        raise RunnerError("unverified_migration", "A matching verified migration receipt is required.")
    result = deepcopy(state)
    history = result.setdefault("migration_history", [])
    if not any(item.get("plan_id") == receipt["plan_id"] and item.get("direction") == receipt["direction"] for item in history):
        history.append(deepcopy(receipt))
    if receipt["direction"] == "forward":
        result["runtime_contract"] = version_record("verified_migration", runner_verified=True,
                                                   plan_id=receipt["plan_id"], receipt_digest=digest(receipt))
    else:
        result["runtime_contract"] = {"schema_version": 1, "versions": None,
                                      "provenance": {"source": "verified_rollback", "plan_id": receipt["plan_id"]}}
    return result

# Frozen, exact generated bodies from the repository history. Not heuristics.
LEGACY_PROMPTS = {'517bbdd': 'Run the next safe phase-gated delivery step for the roadmap recorded in\n`automation/<roadmap-slug>/delivery_state.json`. Resolve the current roadmap\npath from `delivery_state.json`; the state roadmap field is authoritative\nacross lifecycle renames.\n\nRead these files before acting:\n- `automation/<roadmap-slug>/automation_guide.md`\n- `automation/codex_phase_gated_delivery_automation_template.md`\n- `automation/<roadmap-slug>/delivery_state.json`\n- `automation/<roadmap-slug>/delivery_log.md`\n- `automation/<roadmap-slug>/review_fix_state.json`\n- `automation/<roadmap-slug>/phase_model_policy.json`\n- `automation/<roadmap-slug>/approval_policy.json` when present\n- `automation/<roadmap-slug>/phase_prerequisites.json` and\n  `automation/<roadmap-slug>/phase_preflight.md` when present\n\nOperate on exactly one current phase at a time. Resolve the roadmap from state,\nthen reconcile roadmap, state, log, review files, phase model policy, approval\npolicy, branch, worktree status, and saved runner configuration before editing.\n\nBefore recording a generic mismatch blocker, handle the normal paused-setup to\nactive-run transition: if durable setup artifacts still say the saved runner is\nPAUSED but saved readback is ACTIVE, and model/reasoning, cwd, state-first\nprompt, hard-stop guard, and blocked-remediation guard all match, accept it as\noperator/manual activation. Update guide/log/state to ACTIVE, record\n`last_activation` and `last_blocker_repair`, reset stalled counters, rerun\nvalidation, and continue the current phase. Do not stop just because the saved\nrunner is ACTIVE after the operator started it.\n\nValidate approval policy before relying on pre-approved operations. If the\npolicy is missing, use conservative legacy behavior. If the policy is invalid,\nrecord the blocker and stop before delivery work.\n\nBefore delivery starts, read existing phase preflight evidence when present. If\nfuture phases or finalization have no recent preflight evidence, perform a\nread-only scan for later model, credential, network, tooling, external\ndecision, and approval prerequisites. Record mitigations and required operator\nactions without implementing future phases.\n\nIf state is blocked, enter Blocked Remediation Mode before normal delivery.\nHard stop before delivery if all phases are complete, status is completed, or\nstatus is completed_pending_pause. For completed or stalled states, pause the\nsaved runner when `pause_saved_automation` is allowed, a context-specific\npause flag allows it, explicit human approval is present, or the context flag\nis absent and default terminal safety pause applies; generated policies allow\ncompletion and stalled-run safety pauses by default. Always record pause\nreadback evidence.\n\nFor the current phase only, extract objective, owned files, implementation\nsteps, acceptance criteria, required verification, non-goals, and stop\nconditions. Create or reuse the correct phase branch when implementation work\nis required. Verify saved runner model and reasoning against policy before\ndelivery. Make only phase-scoped changes, run required verification, update\nstate/log, write a fresh review, and advance only after the review verdict is\ndelivered.\n\nDo not push or edit runner configuration unless a valid approval policy\nexplicitly allows the operation and readback evidence matches, except for the\nnarrow status-only completion/stall self-pause described above. Do not merge,\npromote, delete branches, install global packages, or run destructive commands\nwithout explicit human approval; approval modes never cover never-auto\noperations.\nAfter advancing state to the next phase, stop.', 'b9155d0': 'Run the next safe phase-gated delivery step for the roadmap recorded in\n`automation/<roadmap-slug>/delivery_state.json`. Resolve the current roadmap\npath from `delivery_state.json`; the state roadmap field is authoritative\nacross lifecycle renames.\n\nRead these files before acting:\n- `automation/<roadmap-slug>/automation_guide.md`\n- `automation/codex_phase_gated_delivery_automation_template.md`\n- `automation/<roadmap-slug>/delivery_state.json`\n- `automation/<roadmap-slug>/delivery_log.md`\n- `automation/<roadmap-slug>/review_fix_state.json`\n- `automation/<roadmap-slug>/phase_model_policy.json`\n- `automation/<roadmap-slug>/approval_policy.json` when present\n\nOperate on exactly one current phase at a time. Resolve the roadmap from state,\nthen reconcile roadmap, state, log, review files, phase model policy, approval\npolicy, branch, worktree status, and saved runner configuration before editing.\n\nValidate approval policy before relying on pre-approved operations. If the\npolicy is missing, use conservative legacy behavior. If the policy is invalid,\nrecord the blocker and stop before delivery work.\n\nIf state is blocked, enter Blocked Remediation Mode before normal delivery.\nHard stop before delivery if all phases are complete, status is completed, or\nstatus is completed_pending_pause. For completed or stalled states, pause the\nsaved runner when `pause_saved_automation` is allowed, a context-specific\npause flag allows it, or explicit human approval is present; generated\npolicies allow completion and stalled-run safety pauses by default. Always\nrecord pause readback evidence.\n\nFor the current phase only, extract objective, owned files, implementation\nsteps, acceptance criteria, required verification, non-goals, and stop\nconditions. Create or reuse the correct phase branch when implementation work\nis required. Verify saved runner model and reasoning against policy before\ndelivery. Make only phase-scoped changes, run required verification, update\nstate/log, write a fresh review, and advance only after the review verdict is\ndelivered.\n\nDo not push or edit runner configuration unless a valid approval policy\nexplicitly allows the operation and readback evidence matches. Do not merge,\npromote, delete branches, install global packages, or run destructive commands\nwithout explicit human approval; approval modes never cover never-auto\noperations.\nAfter advancing state to the next phase, stop.', '9c0d7ae^': 'Run the next safe phase-gated delivery step for `ROADMAP_PATH`.\n\nRead these files before acting:\n- `automation/<roadmap-slug>/automation_guide.md`\n- `automation/codex_phase_gated_delivery_automation_template.md`\n- `automation/<roadmap-slug>/delivery_state.json`\n- `automation/<roadmap-slug>/delivery_log.md`\n- `automation/<roadmap-slug>/review_fix_state.json`\n- `automation/<roadmap-slug>/phase_model_policy.json`\n- `automation/<roadmap-slug>/approval_policy.json` when present\n\nOperate on exactly one current phase at a time. Reconcile roadmap, state, log,\nreview files, phase model policy, approval policy, branch, worktree status, and\nsaved runner configuration before editing.\n\nValidate approval policy before relying on pre-approved operations. If the\npolicy is missing, use conservative legacy behavior. If the policy is invalid,\nrecord the blocker and stop before delivery work.\n\nIf state is blocked, enter Blocked Remediation Mode before normal delivery.\nHard stop before delivery if all phases are complete, status is completed, or\nstatus is completed_pending_pause. For completed or stalled states, pause the\nsaved runner only when `pause_saved_automation` is allowed, a context-specific\npause flag allows it, or explicit human approval is present; always record\npause readback evidence.\n\nFor the current phase only, extract objective, owned files, implementation\nsteps, acceptance criteria, required verification, non-goals, and stop\nconditions. Create or reuse the correct phase branch when implementation work\nis required. Verify saved runner model and reasoning against policy before\ndelivery. Make only phase-scoped changes, run required verification, update\nstate/log, write a fresh review, and advance only after the review verdict is\ndelivered.\n\nDo not push or edit runner configuration unless a valid approval policy\nexplicitly allows the operation and readback evidence matches. Do not merge,\npromote, delete branches, install global packages, or run destructive commands\nwithout explicit human approval; approval modes never cover never-auto\noperations.\nAfter advancing state to the next phase, stop.'}
# Frozen preceding generated prompt; recognition still confers no authority.
LEGACY_PROMPTS["phase-6-v2"] = 'Roadmap delivery prompt-template version: 2\nRun the next safe phase-gated delivery step for the roadmap recorded in\n`automation/<roadmap-slug>/delivery_state.json`. Resolve the current roadmap\npath from `delivery_state.json`; the state roadmap field is authoritative\nacross lifecycle renames.\n\nRead these files before acting:\n- `automation/<roadmap-slug>/automation_guide.md`\n- `automation/codex_phase_gated_delivery_automation_template.md`\n- `automation/<roadmap-slug>/delivery_state.json`\n- `automation/<roadmap-slug>/delivery_log.md`\n- `automation/<roadmap-slug>/review_fix_state.json`\n- `automation/<roadmap-slug>/phase_model_policy.json`\n- `automation/<roadmap-slug>/approval_policy.json` when present\n- `automation/<roadmap-slug>/phase_prerequisites.json` and\n  `automation/<roadmap-slug>/phase_preflight.md` when present\n\nOperate on exactly one current phase at a time. Resolve the roadmap from state,\nthen reconcile roadmap, state, log, review files, phase model policy, approval\npolicy, branch, worktree status, and saved runner configuration before editing.\n\nBefore recording a generic mismatch blocker, handle the normal paused-setup to\nactive-run transition: if durable setup artifacts still say the saved runner is\nPAUSED but saved readback is ACTIVE, and model/reasoning, cwd, state-first\nprompt, hard-stop guard, and blocked-remediation guard all match, accept it as\noperator/manual activation. Update guide/log/state to ACTIVE, record\n`last_activation` and `last_blocker_repair`, reset stalled counters, rerun\nvalidation, and continue the current phase. Do not stop just because the saved\nrunner is ACTIVE after the operator started it.\n\nValidate approval policy before relying on pre-approved operations. If the\npolicy is missing, use conservative legacy behavior. If the policy is invalid,\nrecord the blocker and stop before delivery work.\n\nBefore delivery starts, read existing phase preflight evidence when present. If\nfuture phases or finalization have no recent preflight evidence, perform a\nread-only scan for later model, credential, network, tooling, external\ndecision, and approval prerequisites. Record mitigations and required operator\nactions without implementing future phases.\n\nIf state is blocked, enter Blocked Remediation Mode before normal delivery.\nHard stop before delivery if all phases are complete, status is completed, or\nstatus is completed_pending_pause. For completed or stalled states, the narrow status-only safety pause is\nauthorized by default unless the corresponding context flag is explicitly\nfalse. Explicit operator restrictions take precedence; broad saved-runner edit\nrestrictions alone do not revoke this terminal exception. Preserve every other\nsetting, use supported host tooling, and require authoritative PAUSED readback.\nTerminal handling comes before ordinary model or migration gates. Unknown\nprompt upgrades remain separate operator decisions; do not repeat a pending\nidentical approval question.\n\nFor the current phase only, extract objective, owned files, implementation\nsteps, acceptance criteria, required verification, non-goals, and stop\nconditions. Create or reuse the correct phase branch when implementation work\nis required. Verify saved runner model and reasoning against policy before\ndelivery. Make only phase-scoped changes, run required verification, update\nstate/log, write a fresh review, and advance only after the review verdict is\ndelivered.\n\nDo not push or edit runner configuration unless a valid approval policy\nexplicitly allows the operation and readback evidence matches, except for the\nnarrow status-only completion/stall self-pause described above. Do not merge,\npromote, delete branches, install global packages, or run destructive commands\nwithout explicit human approval; approval modes never cover never-auto\noperations.\nAfter advancing state to the next phase, stop.'
CURRENT_PROMPT = 'Roadmap delivery prompt-template version: 3\nRun the next safe phase-gated delivery step for the roadmap recorded in\n`automation/<roadmap-slug>/delivery_state.json`. Resolve the current roadmap\npath from `delivery_state.json`; the state roadmap field is authoritative\nacross lifecycle renames.\n\nRead these files before acting:\n- `automation/<roadmap-slug>/automation_guide.md`\n- `automation/codex_phase_gated_delivery_automation_template.md`\n- `automation/<roadmap-slug>/delivery_state.json`\n- `automation/<roadmap-slug>/delivery_log.md`\n- `automation/<roadmap-slug>/review_fix_state.json`\n- `automation/<roadmap-slug>/phase_model_policy.json`\n- `automation/<roadmap-slug>/approval_policy.json` when present\n- `automation/<roadmap-slug>/phase_prerequisites.json` and\n  `automation/<roadmap-slug>/phase_preflight.md` when present\n\nOperate on exactly one current phase at a time. Resolve the roadmap from state,\nthen reconcile roadmap, state, log, review files, phase model policy, approval\npolicy, branch, worktree status, and saved runner configuration before editing.\n\nBefore recording a generic mismatch blocker, handle the normal paused-setup to\nactive-run transition: if durable setup artifacts still say the saved runner is\nPAUSED but saved readback is ACTIVE, and model/reasoning, cwd, state-first\nprompt, hard-stop guard, and blocked-remediation guard all match, accept it as\noperator/manual activation. Update guide/log/state to ACTIVE, record\n`last_activation` and any verified original-cause repair, preserve stall counters, rerun\nvalidation, and continue the current phase. Do not stop just because the saved\nrunner is ACTIVE after the operator started it.\n\nValidate approval policy before relying on pre-approved operations. If the\npolicy is missing, use conservative legacy behavior. If the policy is invalid,\nrecord the blocker and stop before delivery work.\n\nBefore delivery starts, read existing phase preflight evidence when present. If\nfuture phases or finalization have no recent preflight evidence, perform a\nread-only scan for later model, credential, network, tooling, external\ndecision, and approval prerequisites. Record mitigations and required operator\nactions without implementing future phases.\n\nIf status is blocked, enter Blocked Remediation Mode before normal delivery.\nClassify the original blocker; repair only local or already-authorized causes,\nrerun validation and clear the reason only after verified repair.\nHard stop before delivery if all phases are complete, status is completed, or\nstatus is completed_pending_pause. For completed or stalled states, the narrow status-only safety pause is\nauthorized by default unless the corresponding context flag is explicitly\nfalse. Explicit operator restrictions take precedence; broad saved-runner edit\nrestrictions alone do not revoke this terminal exception. Preserve every other\nsetting, use supported host tooling, and require authoritative PAUSED readback.\nTerminal handling comes before ordinary model or migration gates. Unknown\nprompt upgrades remain separate operator decisions; do not repeat a pending\nidentical approval question.\n\nFor the current phase only, extract objective, owned files, implementation\nsteps, acceptance criteria, required verification, non-goals, and stop\nconditions. Create or reuse the correct phase branch when implementation work\nis required. Verify saved runner model and reasoning against policy before\ndelivery. Make only phase-scoped changes, run required verification, update\nstate/log, write a fresh review, and advance only after the review verdict is\ndelivered.\n\nDo not push or edit runner configuration unless a valid approval policy\nexplicitly allows the operation and readback evidence matches, except for the\nnarrow status-only completion/stall self-pause described above. Do not merge,\npromote, delete branches, install global packages, or run destructive commands\nwithout explicit human approval; approval modes never cover never-auto\noperations.\nAfter advancing state to the next phase, stop.'
