#!/usr/bin/env python3
"""Plan future phase prerequisites without mutating delivery state."""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_AUTOMATIONS_DIR = Path.home() / ".codex" / "automations"
AUTOMATIONS_DIR = Path(os.environ.get("AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR", str(DEFAULT_AUTOMATIONS_DIR))).expanduser()

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

APPROVAL_MODES = ("conservative", "delegated_local", "delegated_delivery", "custom")
REASONING_ORDER = ("minimal", "low", "medium", "high", "xhigh")
ENV_VAR_RE = re.compile(
    r"\b(?:[A-Z][A-Z0-9]*_)*(?:API_KEY|TOKEN|SECRET|CREDENTIALS|PASSWORD|ACCESS_KEY|PRIVATE_KEY|DATABASE_URL|DSN)\b"
)
PHASE_HEADING_RE = re.compile(r"^#{2,3}\s+Phase\s+(\d+)\s*(?:[-:]\s*)?(.+?)\s*$", re.IGNORECASE)
FINALIZATION_HEADING_RE = re.compile(r"^#{2,3}\s+Finalization\b(?:\s*[-:]\s*(.+?))?\s*$", re.IGNORECASE)

NETWORK_TERMS = (
    "network",
    "internet",
    "external api",
    "api call",
    "openai api",
    "download",
    "upload",
    "fetch",
    "curl",
    "wget",
    "pip install",
    "npm install",
    "pnpm install",
    "yarn install",
    "git push",
    "github",
    "http://",
    "https://",
    "cloud run",
)

KNOWN_COMMANDS = {
    "bash",
    "cargo",
    "curl",
    "gh",
    "git",
    "go",
    "make",
    "node",
    "npm",
    "npx",
    "pnpm",
    "pytest",
    "python",
    "python3",
    "sh",
    "uv",
    "wget",
    "yarn",
}


def unique(items: Iterable[Any]) -> List[Any]:
    seen = set()
    out: List[Any] = []
    for item in items:
        key = json.dumps(item, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
        if key not in seen:
            out.append(item)
            seen.add(key)
    return out


def unique_paths(paths: Iterable[Path]) -> List[Path]:
    seen = set()
    out: List[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen:
            out.append(path)
            seen.add(key)
    return out


def finding(code: str, severity: str, message: str, mitigation: str = "", **extra: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
    }
    if mitigation:
        result["mitigation"] = mitigation
    result.update({key: value for key, value in extra.items() if value is not None})
    return result


def slug_forms(slug: Optional[str]) -> Dict[str, Optional[str]]:
    if not slug:
        return {"input": None, "dash": None, "dir": None}
    return {
        "input": slug,
        "dash": slug.replace("_", "-"),
        "dir": slug.replace("-", "_"),
    }


def resolve_repo_path(repo_root: Path, value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return repo_root / path


def state_candidates(repo_root: Path, forms: Dict[str, Optional[str]]) -> List[Path]:
    candidates: List[Path] = []
    for slug in unique([item for item in (forms.get("dir"), forms.get("dash")) if item]):
        candidates.append(repo_root / "roadmaps" / "automation" / str(slug) / "delivery_state.json")
        candidates.append(repo_root / "automation" / str(slug) / "delivery_state.json")
    return unique_paths(candidates)


def automation_dir_candidates(repo_root: Path, forms: Dict[str, Optional[str]]) -> List[Path]:
    candidates: List[Path] = []
    for slug in unique([item for item in (forms.get("dir"), forms.get("dash")) if item]):
        candidates.append(repo_root / "roadmaps" / "automation" / str(slug))
        candidates.append(repo_root / "automation" / str(slug))
    return unique_paths(candidates)


def load_json_object(path: Path, errors: List[Dict[str, Any]], label: str) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(finding(f"invalid_{label}_json", "blocker", f"{path}: invalid JSON: {exc}", path=str(path)))
        return None
    except OSError as exc:
        errors.append(finding(f"{label}_unreadable", "blocker", f"{path}: cannot read file: {exc}", path=str(path)))
        return None
    if not isinstance(value, dict):
        errors.append(finding(f"invalid_{label}_shape", "blocker", f"{path}: JSON root is not an object.", path=str(path)))
        return None
    return value


def parse_minimal_toml(path: Path) -> Dict[str, Any]:
    try:
        import tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore

    if tomllib is not None:
        with path.open("rb") as fh:
            return tomllib.load(fh)

    data: Dict[str, Any] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            continue
        if value.startswith("[") and value.endswith("]"):
            try:
                data[key] = ast.literal_eval(value)
            except (SyntaxError, ValueError):
                data[key] = value
            continue
        if value.startswith(("'", '"')):
            try:
                data[key] = ast.literal_eval(value)
            except (SyntaxError, ValueError):
                data[key] = value.strip("'\"")
            continue
        if value.lower() in ("true", "false"):
            data[key] = value.lower() == "true"
            continue
        try:
            data[key] = int(value)
        except ValueError:
            data[key] = value
    return data


def approved_operations_for_mode(mode: str, custom_operations: Optional[Dict[str, bool]] = None) -> Dict[str, bool]:
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


def default_approval_policy() -> Dict[str, Any]:
    operations = approved_operations_for_mode("conservative")
    return {
        "path": None,
        "present": False,
        "fallback": "conservative",
        "fallback_reason": "missing_policy",
        "approval_mode": "conservative",
        "approved_operations": approved_operation_names(operations),
        "operations": operations,
        "operation_decisions": {
            operation: approval_decision_for_operation(operations, operation)
            for operation in [*OPERATIONS, *FORBIDDEN_NAMED_OPERATIONS]
        },
        "errors": [],
    }


def approval_policy_path(repo_root: Path, state_file: Optional[Path], state: Dict[str, Any]) -> Optional[Path]:
    value = state.get("approval_policy_path")
    if isinstance(value, str) and value.strip():
        return resolve_repo_path(repo_root, value)
    if state_file is not None:
        return state_file.parent / "approval_policy.json"
    return None


def read_approval_policy(repo_root: Path, state_file: Optional[Path], state: Dict[str, Any]) -> Dict[str, Any]:
    policy_path = approval_policy_path(repo_root, state_file, state)
    if policy_path is None or not policy_path.exists():
        report = default_approval_policy()
        report["path"] = str(policy_path) if policy_path is not None else None
        return report

    errors: List[Dict[str, Any]] = []
    policy = load_json_object(policy_path, errors, "approval_policy")
    if policy is None:
        report = default_approval_policy()
        report.update(
            {
                "path": str(policy_path),
                "present": True,
                "fallback_reason": "invalid_or_unreadable_policy",
                "errors": errors,
            }
        )
        return report

    mode = policy.get("approval_mode")
    raw_operations = policy.get("operations")
    if mode not in APPROVAL_MODES or not isinstance(raw_operations, dict):
        report = default_approval_policy()
        report.update(
            {
                "path": str(policy_path),
                "present": True,
                "fallback_reason": "invalid_policy",
                "errors": [
                    finding(
                        "invalid_approval_policy",
                        "blocker",
                        "approval_policy.json must define a supported approval_mode and operations object.",
                        path=str(policy_path),
                    )
                ],
            }
        )
        return report

    custom_operations = {key: bool(value) for key, value in raw_operations.items() if key in OPERATIONS and isinstance(value, bool)}
    operations = approved_operations_for_mode(str(mode), custom_operations if mode == "custom" else None)
    return {
        "path": str(policy_path),
        "present": True,
        "fallback": None,
        "fallback_reason": None,
        "approval_mode": mode,
        "approved_operations": approved_operation_names(operations),
        "operations": operations,
        "operation_decisions": {
            operation: approval_decision_for_operation(operations, operation)
            for operation in [*OPERATIONS, *FORBIDDEN_NAMED_OPERATIONS]
        },
        "errors": [],
    }


def choose_state(args: argparse.Namespace, repo_root: Path, forms: Dict[str, Optional[str]], errors: List[Dict[str, Any]]) -> Tuple[Optional[Path], Dict[str, Any]]:
    if args.state_file:
        state_path = resolve_repo_path(repo_root, args.state_file)
        if state_path is None:
            return None, {}
        state = load_json_object(state_path, errors, "state")
        return state_path, state or {}

    for candidate in state_candidates(repo_root, forms):
        if candidate.exists():
            state = load_json_object(candidate, errors, "state")
            return candidate, state or {}

    if args.roadmap_slug:
        errors.append(
            finding(
                "state_file_missing",
                "warning",
                "No delivery_state.json was found for the selected roadmap slug; preflight will rely on explicit arguments only.",
            )
        )
    return None, {}


def find_automation_toml(args: argparse.Namespace, forms: Dict[str, Optional[str]]) -> Optional[Path]:
    if args.automation_config:
        return Path(args.automation_config).expanduser().resolve()

    candidates: List[Path] = []
    if args.automation_id:
        candidates.append(AUTOMATIONS_DIR / args.automation_id / "automation.toml")
    for slug in unique([item for item in (forms.get("dash"), forms.get("dir")) if item]):
        candidates.append(AUTOMATIONS_DIR / f"{slug}-delivery" / "automation.toml")

    for candidate in unique_paths(candidates):
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else None


def resolve_roadmap_path(
    args: argparse.Namespace,
    repo_root: Path,
    state: Dict[str, Any],
    errors: List[Dict[str, Any]],
) -> Optional[Path]:
    explicit = resolve_repo_path(repo_root, args.roadmap)
    if explicit is not None:
        return explicit
    from_state = resolve_repo_path(repo_root, state.get("roadmap") if isinstance(state.get("roadmap"), str) else None)
    if from_state is not None:
        return from_state
    errors.append(
        finding(
            "roadmap_path_missing",
            "blocker",
            "No roadmap path was provided and delivery_state.json does not define roadmap.",
            "Pass --roadmap or ensure delivery_state.json records the roadmap path.",
        )
    )
    return None


def parse_roadmap_phases(roadmap_path: Path, errors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    try:
        lines = roadmap_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        errors.append(finding("roadmap_unreadable", "blocker", f"Cannot read roadmap: {exc}", path=str(roadmap_path)))
        return []

    phases: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    body: List[str] = []

    def flush() -> None:
        nonlocal current, body
        if current is not None:
            current["body"] = "\n".join(body).strip()
            phases.append(current)
        current = None
        body = []

    for line_number, line in enumerate(lines, start=1):
        phase_match = PHASE_HEADING_RE.match(line)
        finalization_match = FINALIZATION_HEADING_RE.match(line)
        if phase_match or finalization_match:
            flush()
            if phase_match:
                number = int(phase_match.group(1))
                title = phase_match.group(2).strip()
                heading = f"Phase {number} - {title}" if title else f"Phase {number}"
                current = {
                    "key": str(number),
                    "phase_number": number,
                    "phase": heading,
                    "title": title,
                    "heading": line.strip(),
                    "line": line_number,
                }
            else:
                title = (finalization_match.group(1) or "").strip()
                current = {
                    "key": "finalization",
                    "phase_number": None,
                    "phase": "Finalization" if not title else f"Finalization - {title}",
                    "title": title,
                    "heading": line.strip(),
                    "line": line_number,
                }
            continue
        if current is not None:
            body.append(line)
    flush()
    return phases


def phase_number(value: Any) -> Optional[int]:
    match = re.search(r"\bPhase\s+(\d+)\b", str(value or ""), re.IGNORECASE)
    return int(match.group(1)) if match else None


def reasoning_satisfies(configured: Any, required: Any) -> bool:
    if not required:
        return True
    if not configured:
        return False
    configured_text = str(configured).strip().lower()
    required_text = str(required).strip().lower()
    if configured_text not in REASONING_ORDER or required_text not in REASONING_ORDER:
        return configured_text == required_text
    return REASONING_ORDER.index(configured_text) >= REASONING_ORDER.index(required_text)


def resolve_policy_target(policy: Dict[str, Any], phase_key: str) -> Dict[str, Any]:
    defaults = policy.get("defaults") if isinstance(policy.get("defaults"), dict) else {}
    phases = policy.get("phases") if isinstance(policy.get("phases"), dict) else {}
    override = phases.get(phase_key)
    if not isinstance(override, dict):
        override = {}
        source = "defaults"
    else:
        source = f"phases.{phase_key}"
    return {
        "source": source,
        "model": override.get("model") or defaults.get("model"),
        "reasoning_effort": override.get("reasoning_effort") or defaults.get("reasoning_effort"),
    }


def code_fence_commands(body: str) -> List[str]:
    commands: List[str] = []
    in_fence = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and stripped and not stripped.startswith("#"):
            commands.append(stripped)
    return commands


def backtick_commands(body: str) -> List[str]:
    commands: List[str] = []
    for value in re.findall(r"`([^`\n]+)`", body):
        candidate = value.strip()
        first = first_command_token(candidate)
        if first and (first in KNOWN_COMMANDS or first.startswith("./") or first.endswith(".py")):
            commands.append(candidate)
    return commands


def first_command_token(command: str) -> Optional[str]:
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    for part in parts:
        if re.match(r"^[A-Z_][A-Z0-9_]*=.*", part):
            continue
        return part
    return None


def command_requires_network(command: str) -> bool:
    lower = command.lower()
    return any(
        token in lower
        for token in (
            "curl ",
            "wget ",
            "pip install",
            "npm install",
            "pnpm install",
            "yarn install",
            "git push",
            "gh ",
        )
    )


def detect_env_vars(body: str) -> List[str]:
    names = set(ENV_VAR_RE.findall(body))
    lower = body.lower()
    if "openai api" in lower or "full extraction" in lower or ("openai" in lower and "api" in lower):
        names.add("OPENAI_API_KEY")
    return sorted(names)


def detect_operations(body: str) -> List[str]:
    lower = body.lower()
    operations: List[str] = []
    checks: Sequence[Tuple[str, Sequence[str]]] = (
        ("commit_delivered_phase_locally", ("git commit", "local commit", "commit changes", "commit delivered")),
        ("push_current_phase_branch", ("git push", "push current branch", "push branch", "push to github", "publish branch")),
        ("retarget_saved_automation", ("retarget", "saved automation config", "automation config", "runner configuration", "model/reasoning", "reasoning effort")),
        ("pause_saved_automation", ("pause automation", "pause saved", "pause runner", "status-only pause")),
        ("sync_installed_skill", ("sync installed skill", "installed skill sync", "install global", "global package", "installed plugin sync")),
        ("publish_release_or_package", ("publish release", "package registry", "marketplace submission", "release registry")),
        ("promote_to_main", ("promote to main", "merge to main", "merge into main", "main promotion")),
        ("destructive_git", ("reset --hard", "force push", "delete branch", "delete tag", "rewrite history")),
    )
    for operation, needles in checks:
        if any(needle in lower for needle in needles):
            operations.append(operation)
    if detect_env_vars(body) or "credential" in lower or "secret" in lower:
        operations.append("use_credentials")
    return unique(operations)


def body_requires_network(body: str, commands: Sequence[str]) -> bool:
    lower = body.lower()
    return any(term in lower for term in NETWORK_TERMS) or any(command_requires_network(command) for command in commands)


def add_approval_issue(
    phase: Dict[str, Any],
    approval_policy: Dict[str, Any],
    operation: str,
    context: str,
) -> None:
    decision = approval_decision_for_operation(approval_policy.get("operations", {}), operation)
    phase["approvals"].append({**decision, "context": context})
    if decision["decision"] == "ask":
        phase["issues"].append(
            finding(
                "approval_required",
                "approval",
                f"{operation} is needed for {context}, but approval policy does not pre-approve it.",
                f"Pre-approve {operation} in approval_policy.json or plan an explicit operator stop before this phase.",
                operation=operation,
                decision=decision["decision"],
            )
        )
    elif decision["decision"] == "forbidden":
        phase["issues"].append(
            finding(
                "forbidden_operation",
                "blocker",
                f"{operation} is needed for {context}, but policy classifies it as forbidden.",
                "Split this into a human-run action or change the roadmap so automation does not perform it.",
                operation=operation,
                decision=decision["decision"],
            )
        )


def analyze_phase(
    phase: Dict[str, Any],
    *,
    approval_policy: Dict[str, Any],
    phase_model_policy: Dict[str, Any],
    automation_data: Dict[str, Any],
    automation_toml: Optional[Path],
    state: Dict[str, Any],
    network_disabled: bool,
) -> Dict[str, Any]:
    body = str(phase.get("body") or "")
    commands = unique([*code_fence_commands(body), *backtick_commands(body)])
    checked_env: List[Dict[str, Any]] = []
    result = {
        **{key: value for key, value in phase.items() if key != "body"},
        "readiness": "ready",
        "issues": [],
        "approvals": [],
        "environment": checked_env,
        "commands": commands,
        "model_target": None,
    }

    for env_var in detect_env_vars(body):
        present = bool(os.environ.get(env_var))
        checked_env.append({"name": env_var, "present": present})
        if not present:
            result["issues"].append(
                finding(
                    "missing_environment_variable",
                    "blocker",
                    f"{env_var} is referenced by the phase but is not set in the current runtime.",
                    f"Set {env_var} in the automation runtime before activation, or add an explicit offline fixture/dry-run path.",
                    name=env_var,
                )
            )

    if checked_env:
        add_approval_issue(result, approval_policy, "use_credentials", "credential-backed phase work")

    network_required = body_requires_network(body, commands)
    result["network_required"] = network_required
    if network_required and network_disabled:
        result["issues"].append(
            finding(
                "network_disabled",
                "blocker",
                "The phase appears to require network/API access, but CODEX_SANDBOX_NETWORK_DISABLED=1.",
                "Use a network-enabled execution surface, prefetch required inputs, or split the phase into offline prep plus an approved live run.",
                env="CODEX_SANDBOX_NETWORK_DISABLED",
            )
        )

    for command in commands:
        token = first_command_token(command)
        if not token or token.startswith("./") or "/" in token:
            continue
        if token in KNOWN_COMMANDS and shutil.which(token) is None:
            result["issues"].append(
                finding(
                    "missing_local_tool",
                    "mitigation",
                    f"Required command {token!r} is not available on PATH.",
                    f"Install or select a runner with {token!r} available before this phase, or adjust verification to use an available tool.",
                    command=command,
                    tool=token,
                )
            )

    for operation in detect_operations(body):
        add_approval_issue(result, approval_policy, operation, "phase text")

    if phase_model_policy:
        target = resolve_policy_target(phase_model_policy, str(phase.get("key")))
        if target.get("model") or target.get("reasoning_effort"):
            configured_model = automation_data.get("model") or state.get("configured_automation_model")
            configured_reasoning = automation_data.get("reasoning_effort") or state.get("configured_automation_reasoning_effort")
            target.update(
                {
                    "configured_model": configured_model,
                    "configured_reasoning_effort": configured_reasoning,
                    "automation_toml": str(automation_toml) if automation_toml and automation_toml.exists() else None,
                }
            )
            result["model_target"] = target
            model_mismatch = bool(target.get("model") and configured_model and str(target["model"]) != str(configured_model))
            reasoning_mismatch = bool(
                target.get("reasoning_effort")
                and configured_reasoning
                and not reasoning_satisfies(configured_reasoning, target["reasoning_effort"])
            )
            readback_missing = bool((target.get("model") and not configured_model) or (target.get("reasoning_effort") and not configured_reasoning))
            if readback_missing:
                result["issues"].append(
                    finding(
                        "runner_readback_missing",
                        "blocker",
                        "Phase model policy defines a required runner target, but model/reasoning readback is unavailable.",
                        "Read back saved automation configuration before activation, or run manually with explicit model and reasoning settings.",
                    )
                )
            elif model_mismatch or reasoning_mismatch:
                configured = f"{configured_model or 'unknown'} / {configured_reasoning or 'unknown'}"
                required = f"{target.get('model') or 'unknown'} / {target.get('reasoning_effort') or 'unknown'}"
                result["issues"].append(
                    finding(
                        "runner_retarget_needed",
                        "approval",
                        f"Saved runner readback is {configured}, but this phase requires {required}.",
                        "Pre-approve retarget_saved_automation, retarget the saved runner, read back the config, and stop so the next run starts correctly.",
                        operation="retarget_saved_automation",
                    )
                )
                add_approval_issue(result, approval_policy, "retarget_saved_automation", "future phase model policy")

    severities = {issue.get("severity") for issue in result["issues"]}
    if "blocker" in severities:
        result["readiness"] = "blocked"
    elif "approval" in severities:
        result["readiness"] = "needs_approval"
    elif "mitigation" in severities or "warning" in severities:
        result["readiness"] = "needs_mitigation"
    return result


def load_phase_model_policy(
    repo_root: Path,
    state_file: Optional[Path],
    forms: Dict[str, Optional[str]],
    errors: List[Dict[str, Any]],
) -> Tuple[Optional[Path], Dict[str, Any]]:
    candidates: List[Path] = []
    if state_file is not None:
        candidates.append(state_file.parent / "phase_model_policy.json")
    for automation_dir in automation_dir_candidates(repo_root, forms):
        candidates.append(automation_dir / "phase_model_policy.json")
    for candidate in unique_paths(candidates):
        if candidate.exists():
            policy = load_json_object(candidate, errors, "phase_model_policy")
            return candidate, policy or {}
    return (candidates[0] if candidates else None), {}


def load_automation_data(automation_toml: Optional[Path], errors: List[Dict[str, Any]]) -> Dict[str, Any]:
    if automation_toml is None or not automation_toml.exists():
        return {}
    try:
        return parse_minimal_toml(automation_toml)
    except OSError as exc:
        errors.append(finding("automation_config_unreadable", "blocker", f"Cannot read automation config: {exc}", path=str(automation_toml)))
        return {}


def build_operator_actions(phases: Sequence[Dict[str, Any]], top_warnings: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for warning in top_warnings:
        if warning.get("code") == "approval_policy_missing":
            actions.append(
                {
                    "phase": "setup",
                    "code": warning["code"],
                    "action": "Create approval_policy.json before activation so retarget, commit, push, pause, and publication decisions are explicit.",
                }
            )
    for phase in phases:
        for issue in phase.get("issues", []):
            mitigation = issue.get("mitigation")
            if not mitigation:
                continue
            actions.append(
                {
                    "phase": phase.get("phase"),
                    "code": issue.get("code"),
                    "operation": issue.get("operation"),
                    "name": issue.get("name"),
                    "action": mitigation,
                }
            )
    return unique(actions)


def summarize(phases: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    counts: Dict[str, int] = {
        "phase_count": len(phases),
        "ready": 0,
        "needs_mitigation": 0,
        "needs_approval": 0,
        "blocked": 0,
    }
    issue_count = 0
    for phase in phases:
        readiness = str(phase.get("readiness") or "ready")
        if readiness not in counts:
            counts[readiness] = 0
        counts[readiness] += 1
        issue_count += len(phase.get("issues", []))
    counts["issue_count"] = issue_count
    return counts


def build_report(args: argparse.Namespace) -> Dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    forms = slug_forms(args.roadmap_slug)
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    state_file, state = choose_state(args, repo_root, forms, errors)
    approval_policy = read_approval_policy(repo_root, state_file, state)
    errors.extend(approval_policy.get("errors", []))
    if not approval_policy.get("present"):
        warnings.append(
            finding(
                "approval_policy_missing",
                "warning",
                "approval_policy.json is missing; conservative fallback will require approval for commits, pushes, retargets, pauses, and delivery operations.",
                "Create approval_policy.json before activating unattended delivery.",
                path=approval_policy.get("path"),
            )
        )

    roadmap_path = resolve_roadmap_path(args, repo_root, state, errors)
    phases = parse_roadmap_phases(roadmap_path, errors) if roadmap_path is not None else []
    current_number = phase_number(state.get("current_phase"))
    phase_model_policy_path, phase_model_policy = load_phase_model_policy(repo_root, state_file, forms, errors)
    automation_toml = find_automation_toml(args, forms)
    automation_data = load_automation_data(automation_toml, errors)
    network_disabled = os.environ.get("CODEX_SANDBOX_NETWORK_DISABLED") == "1"

    analyzed: List[Dict[str, Any]] = []
    for phase in phases:
        number = phase.get("phase_number")
        phase["position"] = "current_or_future"
        if current_number is not None and isinstance(number, int):
            phase["position"] = "past" if number < current_number else ("current" if number == current_number else "future")
        analyzed.append(
            analyze_phase(
                phase,
                approval_policy=approval_policy,
                phase_model_policy=phase_model_policy,
                automation_data=automation_data,
                automation_toml=automation_toml,
                state=state,
                network_disabled=network_disabled,
            )
        )

    summary = summarize(analyzed)
    status = "ok"
    if errors:
        status = "error"
    elif summary.get("blocked"):
        status = "needs_operator_setup"
    elif summary.get("needs_approval") or summary.get("needs_mitigation") or warnings:
        status = "warning"

    return {
        "schema_version": 1,
        "command": "phase-preflight",
        "status": status,
        "repo_root": str(repo_root),
        "roadmap_slug": args.roadmap_slug,
        "automation_id": args.automation_id,
        "state_file": str(state_file) if state_file else None,
        "roadmap": str(roadmap_path) if roadmap_path else None,
        "phase_model_policy": str(phase_model_policy_path) if phase_model_policy_path else None,
        "automation": {
            "toml": str(automation_toml) if automation_toml else None,
            "toml_present": bool(automation_toml and automation_toml.exists()),
            "configured_model": automation_data.get("model") or state.get("configured_automation_model"),
            "configured_reasoning_effort": automation_data.get("reasoning_effort") or state.get("configured_automation_reasoning_effort"),
            "status": automation_data.get("status"),
        },
        "environment": {
            "CODEX_SANDBOX_NETWORK_DISABLED": os.environ.get("CODEX_SANDBOX_NETWORK_DISABLED"),
            "network_disabled": network_disabled,
        },
        "approval_policy": approval_policy,
        "summary": summary,
        "operator_actions": build_operator_actions(analyzed, warnings),
        "phases": analyzed,
        "warnings": warnings,
        "errors": errors,
        "output_files": [],
    }


def resolve_output_path(repo_root: Path, value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return repo_root / path


def markdown_report(report: Dict[str, Any]) -> str:
    lines: List[str] = [
        "# Phase Preflight",
        "",
        f"Status: `{report.get('status')}`",
        f"Roadmap: `{report.get('roadmap')}`",
        f"State: `{report.get('state_file')}`",
        "",
    ]
    actions = report.get("operator_actions") or []
    if actions:
        lines.extend(["## Operator Actions", ""])
        for action in actions:
            label = action.get("phase") or "setup"
            suffix = f" ({action.get('operation')})" if action.get("operation") else ""
            lines.append(f"- {label}{suffix}: {action.get('action')}")
        lines.append("")

    lines.extend(["## Phases", ""])
    for phase in report.get("phases", []):
        lines.append(f"### {phase.get('phase')}")
        lines.append(f"Readiness: `{phase.get('readiness')}`")
        issues = phase.get("issues") or []
        if not issues:
            lines.append("- No preflight issues detected.")
        for issue in issues:
            lines.append(f"- {issue.get('code')}: {issue.get('message')}")
            if issue.get("mitigation"):
                lines.append(f"  Mitigation: {issue.get('mitigation')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(report: Dict[str, Any], args: argparse.Namespace) -> None:
    repo_root = Path(report["repo_root"])
    output_json = resolve_output_path(repo_root, args.output_json)
    output_markdown = resolve_output_path(repo_root, args.output_markdown)
    files = []
    if output_json is not None:
        files.append(str(output_json))
    if output_markdown is not None:
        files.append(str(output_markdown))
    report["output_files"] = files

    for path, content in (
        (output_json, json.dumps(report, indent=2, sort_keys=True) + "\n"),
        (output_markdown, markdown_report(report)),
    ):
        if path is None:
            continue
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            report.setdefault("errors", []).append(
                finding("output_write_failed", "blocker", f"Cannot write {path}: {exc}", path=str(path))
            )
            report["status"] = "error"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to the current directory.")
    parser.add_argument("--roadmap", help="Roadmap path. Defaults to the path recorded in delivery_state.json.")
    parser.add_argument("--roadmap-slug", help="Roadmap slug, accepting dash or underscore form.")
    parser.add_argument("--automation-id", help="Codex automation id under ~/.codex/automations.")
    parser.add_argument("--state-file", help="Explicit delivery_state.json path.")
    parser.add_argument("--automation-config", help="Explicit saved automation.toml path.")
    parser.add_argument("--output-json", help="Optional JSON report output path.")
    parser.add_argument("--output-markdown", help="Optional Markdown report output path.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when preflight finds blockers or approvals.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_report(args)
    write_outputs(report, args)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(markdown_report(report), end="")
    if report.get("errors"):
        return 1
    if args.strict and report.get("status") != "ok":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
