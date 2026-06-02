"""Approval policy helpers for roadmap automation setup, validation, and gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .paths import resolve_repo_path


APPROVAL_MODES = ("conservative", "delegated_local", "delegated_delivery", "custom")

OPERATIONS = (
    "edit_phase_owned_files",
    "write_state_log_review_artifacts",
    "create_or_switch_phase_branch",
    "run_verification",
    "commit_delivered_phase_locally",
    "retarget_saved_automation",
    "pause_saved_automation",
    "push_current_phase_branch",
)

SAFETY_PAUSE_FLAGS = (
    "pause_automation_on_completion",
    "pause_automation_on_stall",
)

DEFAULT_PAUSE_ON_COMPLETION = True
DEFAULT_PAUSE_ON_STALL = True

BASE_LOCAL_OPERATIONS = frozenset(
    {
        "edit_phase_owned_files",
        "write_state_log_review_artifacts",
        "create_or_switch_phase_branch",
        "run_verification",
    }
)

LOCAL_DELEGATED_OPERATIONS = frozenset(
    {
        "commit_delivered_phase_locally",
        "retarget_saved_automation",
        "pause_saved_automation",
    }
)

DELIVERY_DELEGATED_OPERATIONS = frozenset({"push_current_phase_branch"})

NEVER_AUTO_OPERATIONS = (
    "force_push",
    "git_reset_hard",
    "delete_branches_or_tags",
    "merge_or_promote_to_main",
    "publish_releases_or_packages",
    "use_unavailable_credentials",
    "change_repository_security_or_billing",
    "install_or_sync_global_tools",
    "destructive_filesystem_outside_phase_scope",
)

FORBIDDEN_NAMED_OPERATIONS = {
    "sync_installed_skill": "Installed skill or plugin synchronization is never automatic.",
    "publish_release_or_package": "Publication to release or package registries is never automatic.",
    "promote_to_main": "Merging or promoting work to main is never automatic.",
    "use_credentials": "Credential use requires explicit human approval and available credentials.",
    "destructive_git": "Destructive git operations are never automatic.",
}

NEVER_AUTO_REASONS = {
    "force_push": "Force push is never automatic.",
    "git_reset_hard": "git reset --hard is never automatic.",
    "delete_branches_or_tags": "Deleting branches or tags is never automatic.",
    "merge_or_promote_to_main": "Merging or promoting work to main is never automatic.",
    "publish_releases_or_packages": "Publication to releases or package registries is never automatic.",
    "use_unavailable_credentials": "Credentials unavailable to the runner cannot be used automatically.",
    "change_repository_security_or_billing": "Repository security, visibility, permissions, secrets, or billing changes are never automatic.",
    "install_or_sync_global_tools": "Installing or syncing global tools, skills, or plugins is never automatic.",
    "destructive_filesystem_outside_phase_scope": "Destructive filesystem operations outside phase-owned paths are never automatic.",
}

APPROVAL_OPERATION_NAMES = OPERATIONS + tuple(FORBIDDEN_NAMED_OPERATIONS) + NEVER_AUTO_OPERATIONS


def approved_operations_for_mode(
    mode: str,
    custom_operations: Optional[Dict[str, bool]] = None,
) -> Dict[str, bool]:
    """Return the effective operation map for an approval mode."""

    if mode == "conservative":
        allowed = set(BASE_LOCAL_OPERATIONS)
    elif mode == "delegated_local":
        allowed = set(BASE_LOCAL_OPERATIONS | LOCAL_DELEGATED_OPERATIONS)
    elif mode == "delegated_delivery":
        allowed = set(BASE_LOCAL_OPERATIONS | LOCAL_DELEGATED_OPERATIONS | DELIVERY_DELEGATED_OPERATIONS)
    elif mode == "custom":
        custom_operations = custom_operations or {}
        return {operation: bool(custom_operations.get(operation, False)) for operation in OPERATIONS}
    else:
        allowed = set()
    return {operation: operation in allowed for operation in OPERATIONS}


def approved_operation_names(operations: Dict[str, bool]) -> List[str]:
    return [operation for operation in OPERATIONS if operations.get(operation) is True]


def approval_decision_for_operation(operations: Dict[str, bool], operation: str) -> Dict[str, Any]:
    """Return the gate decision for a named operation.

    `allowed` means repository policy pre-approves the operation. `ask` means
    the operation is possible only with explicit human approval. `forbidden`
    means the operation is outside automation policy and must be recorded as a
    blocker instead of being performed automatically.
    """

    if operation in FORBIDDEN_NAMED_OPERATIONS:
        return {
            "operation": operation,
            "decision": "forbidden",
            "reason": FORBIDDEN_NAMED_OPERATIONS[operation],
        }
    if operation in NEVER_AUTO_REASONS:
        return {
            "operation": operation,
            "decision": "forbidden",
            "reason": NEVER_AUTO_REASONS[operation],
        }
    if operation not in OPERATIONS:
        return {
            "operation": operation,
            "decision": "forbidden",
            "reason": "Unknown operation cannot be classified safely.",
        }
    if operations.get(operation) is True:
        return {
            "operation": operation,
            "decision": "allowed",
            "reason": "Approval policy pre-approves this operation.",
        }
    return {
        "operation": operation,
        "decision": "ask",
        "reason": "Approval policy does not pre-approve this operation.",
    }


def approval_decisions_for_operations(operations: Dict[str, bool]) -> Dict[str, Dict[str, Any]]:
    return {
        operation: approval_decision_for_operation(operations, operation)
        for operation in APPROVAL_OPERATION_NAMES
    }


def pause_flags_for_operations(
    operations: Dict[str, bool],
    *,
    pause_on_completion: Optional[bool] = None,
    pause_on_stall: Optional[bool] = None,
) -> Dict[str, bool]:
    pause_allowed = operations.get("pause_saved_automation") is True
    return {
        "pause_automation_on_completion": (
            bool(pause_on_completion)
            if pause_on_completion is not None
            else (pause_allowed or DEFAULT_PAUSE_ON_COMPLETION)
        ),
        "pause_automation_on_stall": (
            bool(pause_on_stall)
            if pause_on_stall is not None
            else (pause_allowed or DEFAULT_PAUSE_ON_STALL)
        ),
    }


def default_approval_policy(
    mode: str = "conservative",
    custom_operations: Optional[Dict[str, bool]] = None,
    *,
    pause_on_completion: Optional[bool] = None,
    pause_on_stall: Optional[bool] = None,
) -> Dict[str, Any]:
    operations = approved_operations_for_mode(mode, custom_operations)
    return {
        "schema_version": 1,
        "approval_mode": mode,
        "operations": operations,
        **pause_flags_for_operations(
            operations,
            pause_on_completion=pause_on_completion,
            pause_on_stall=pause_on_stall,
        ),
        "never_auto": list(NEVER_AUTO_OPERATIONS),
    }


def approval_decision_for_pause_context(policy_report: Dict[str, Any], context: str) -> Dict[str, Any]:
    """Return the approval decision for a completion or stall safety pause."""

    normalized_context = str(context or "").strip().lower().replace("_", "-")
    if normalized_context not in {"completion", "stall"}:
        return {
            "operation": "pause_saved_automation",
            "context": context,
            "decision": "forbidden",
            "reason": "Unknown pause context cannot be classified safely.",
            "source": "context",
        }

    operations = policy_report.get("operations") if isinstance(policy_report, dict) else {}
    if not isinstance(operations, dict):
        operations = {}
    base_decision = approval_decision_for_operation(operations, "pause_saved_automation")
    if base_decision["decision"] != "ask":
        return {
            **base_decision,
            "context": normalized_context,
            "source": "operation",
        }

    flag_name = f"pause_automation_on_{normalized_context}"
    if policy_report.get(flag_name) is True:
        return {
            "operation": "pause_saved_automation",
            "context": normalized_context,
            "decision": "allowed",
            "reason": f"Approval policy explicitly allows automation pause on {normalized_context}.",
            "source": flag_name,
        }
    return {
        **base_decision,
        "context": normalized_context,
        "source": flag_name,
    }


def parse_operation_assignments(values: Optional[Iterable[str]]) -> Tuple[Dict[str, bool], List[Dict[str, str]]]:
    """Parse CLI values shaped as operation=allow|deny|true|false."""

    operations: Dict[str, bool] = {}
    errors: List[Dict[str, str]] = []
    for value in values or []:
        if "=" not in value:
            errors.append(
                {
                    "code": "invalid_approval_operation_flag",
                    "message": f"Approval operation {value!r} must use operation=allow or operation=deny.",
                }
            )
            continue
        key, raw_decision = [part.strip() for part in value.split("=", 1)]
        if key not in OPERATIONS:
            errors.append(
                {
                    "code": "unknown_approval_operation",
                    "message": f"Approval operation {key!r} is not one of {list(OPERATIONS)!r}.",
                }
            )
            continue
        decision = raw_decision.lower()
        if decision in {"allow", "allowed", "true", "yes", "1"}:
            operations[key] = True
        elif decision in {"deny", "denied", "false", "no", "0"}:
            operations[key] = False
        else:
            errors.append(
                {
                    "code": "invalid_approval_operation_decision",
                    "message": f"Approval operation {key!r} has unsupported decision {raw_decision!r}.",
                }
            )
    return operations, errors


def _finding(code: str, message: str, path: Optional[Path] = None) -> Dict[str, str]:
    result = {"code": code, "message": message}
    if path is not None:
        result["path"] = str(path)
    return result


def validate_approval_policy(policy: Any, path: Optional[Path] = None) -> List[Dict[str, str]]:
    errors: List[Dict[str, str]] = []
    if not isinstance(policy, dict):
        return [_finding("invalid_approval_policy_shape", "Approval policy root must be an object.", path)]

    if policy.get("schema_version") != 1:
        errors.append(_finding("invalid_approval_policy_schema_version", "Approval policy schema_version must be 1.", path))

    mode = policy.get("approval_mode")
    if mode not in APPROVAL_MODES:
        errors.append(_finding("invalid_approval_mode", f"approval_mode must be one of {list(APPROVAL_MODES)!r}.", path))

    raw_operations = policy.get("operations")
    if not isinstance(raw_operations, dict):
        errors.append(_finding("invalid_approval_operations", "operations must be an object.", path))
        raw_operations = {}

    custom_operations: Dict[str, bool] = {}
    for operation, decision in raw_operations.items():
        if operation not in OPERATIONS:
            errors.append(_finding("unknown_approval_operation", f"Unknown approval operation {operation!r}.", path))
            continue
        if not isinstance(decision, bool):
            errors.append(_finding("invalid_approval_operation_decision", f"Operation {operation!r} must be boolean.", path))
            continue
        custom_operations[operation] = decision

    if mode == "custom":
        if not raw_operations:
            errors.append(_finding("custom_approval_operations_required", "custom approval mode requires an operations map.", path))
    elif mode in APPROVAL_MODES and mode != "custom" and raw_operations:
        expected = approved_operations_for_mode(str(mode))
        for operation in OPERATIONS:
            if operation in raw_operations and raw_operations.get(operation) != expected[operation]:
                errors.append(
                    _finding(
                        "approval_policy_operations_mismatch",
                        f"Operation {operation!r} does not match the {mode!r} approval mode.",
                        path,
                    )
                )

    raw_never_auto = policy.get("never_auto")
    if not isinstance(raw_never_auto, list):
        errors.append(_finding("invalid_never_auto_operations", "never_auto must be an array.", path))
    else:
        for operation in raw_never_auto:
            if operation not in NEVER_AUTO_OPERATIONS:
                errors.append(_finding("unknown_never_auto_operation", f"Unknown never-auto operation {operation!r}.", path))

    for flag in SAFETY_PAUSE_FLAGS:
        if flag in policy and not isinstance(policy.get(flag), bool):
            errors.append(_finding("invalid_safety_pause_flag", f"{flag} must be boolean when present.", path))

    return errors


def approval_policy_path(repo_root: Path, state_file: Path, state: Dict[str, Any]) -> Path:
    value = state.get("approval_policy_path")
    if isinstance(value, str) and value.strip():
        resolved = resolve_repo_path(repo_root, value)
        if resolved is not None:
            return resolved
    return state_file.parent / "approval_policy.json"


def read_approval_policy(repo_root: Path, state_file: Path, state: Dict[str, Any]) -> Dict[str, Any]:
    path = approval_policy_path(repo_root, state_file, state)
    if not path.exists():
        policy = default_approval_policy("conservative")
        operations = policy["operations"]
        return {
            "path": str(path),
            "present": False,
            "fallback": "conservative",
            "fallback_reason": "missing_policy",
            "approval_mode": "conservative",
            "approved_operations": approved_operation_names(operations),
            "operations": operations,
            "pause_automation_on_completion": policy["pause_automation_on_completion"],
            "pause_automation_on_stall": policy["pause_automation_on_stall"],
            "operation_decisions": approval_decisions_for_operations(operations),
            "errors": [],
        }

    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        operations = approved_operations_for_mode("conservative")
        return {
            "path": str(path),
            "present": True,
            "fallback": "conservative",
            "fallback_reason": "invalid_json",
            "approval_mode": "conservative",
            "approved_operations": approved_operation_names(operations),
            "operations": operations,
            **pause_flags_for_operations(operations),
            "operation_decisions": approval_decisions_for_operations(operations),
            "errors": [_finding("invalid_approval_policy_json", f"Approval policy is invalid JSON: {exc}", path)],
        }
    except OSError as exc:
        operations = approved_operations_for_mode("conservative")
        return {
            "path": str(path),
            "present": True,
            "fallback": "conservative",
            "fallback_reason": "unreadable",
            "approval_mode": "conservative",
            "approved_operations": approved_operation_names(operations),
            "operations": operations,
            **pause_flags_for_operations(operations),
            "operation_decisions": approval_decisions_for_operations(operations),
            "errors": [_finding("approval_policy_unreadable", f"Cannot read approval policy: {exc}", path)],
        }

    errors = validate_approval_policy(policy, path)
    if errors:
        operations = approved_operations_for_mode("conservative")
        return {
            "path": str(path),
            "present": True,
            "fallback": "conservative",
            "fallback_reason": "invalid_policy",
            "approval_mode": "conservative",
            "approved_operations": approved_operation_names(operations),
            "operations": operations,
            **pause_flags_for_operations(operations),
            "operation_decisions": approval_decisions_for_operations(operations),
            "errors": errors,
        }

    mode = str(policy["approval_mode"])
    operations = approved_operations_for_mode(mode, policy.get("operations") if isinstance(policy.get("operations"), dict) else None)
    pause_flags = pause_flags_for_operations(operations)
    return {
        "path": str(path),
        "present": True,
        "fallback": None,
        "fallback_reason": None,
        "approval_mode": mode,
        "approved_operations": approved_operation_names(operations),
        "operations": operations,
        "pause_automation_on_completion": bool(policy.get("pause_automation_on_completion", pause_flags["pause_automation_on_completion"])),
        "pause_automation_on_stall": bool(policy.get("pause_automation_on_stall", pause_flags["pause_automation_on_stall"])),
        "operation_decisions": approval_decisions_for_operations(operations),
        "errors": [],
    }
