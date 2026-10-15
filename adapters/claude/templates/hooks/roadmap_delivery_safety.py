#!/usr/bin/env python3
"""Claude hook helpers for Roadmap Delivery safety checks."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List


# Load the same packaged runtime as helpers; source fallback is development-only.
_hook_root = Path(__file__).resolve().parents[1]
_runtime = _hook_root / "skills/roadmap-delivery-skill/runtime"
if _runtime.is_dir():
    _import_root = _runtime
elif (_hook_root.name == "templates" and _hook_root.parent.name == "claude"
      and _hook_root.parent.parent.name == "adapters"
      and (_hook_root.parents[2] / "pyproject.toml").is_file()):
    _import_root = _hook_root.parents[2] / "src"
else:
    print("Roadmap Delivery hook runtime unavailable; reinstall the complete plugin.", file=sys.stderr)
    raise SystemExit(2)
sys.path.insert(0, str(_import_root))
os.environ.setdefault("AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR",
                      str(Path.home() / ".claude/roadmap-delivery/automations"))
try:
    if sys.version_info[:2] != (3, 12):
        raise ValueError("Safety hooks require Python 3.12 on Claude's PATH.")
    _package_root = _import_root / "roadmap_delivery"
    if not (_package_root / "__init__.py").is_file():
        raise ValueError("The selected runtime package is incomplete.")
    import roadmap_delivery as _runtime_package
    if Path(getattr(_runtime_package, "__file__", None) or "").resolve() != _package_root / "__init__.py":
        raise ValueError("Imported runtime package is outside the selected plugin runtime.")
    from roadmap_delivery import paths as _runtime_paths
    if Path(_runtime_paths.__file__).resolve() != _package_root / "paths.py":
        raise ValueError("Imported resources are outside the selected plugin runtime.")
    _runtime_paths.runtime_resource_root()
    from roadmap_delivery.approval import read_approval_policy
    from roadmap_delivery.reports import build_control_plan, control_plan_for_readback
except (ImportError, ValueError, OSError) as exc:
    print("Roadmap Delivery hook runtime unavailable; reinstall the complete plugin: " + str(exc), file=sys.stderr)
    raise SystemExit(2) from exc


def delivery_plan(cwd: Path, state: Dict[str, Any]) -> Dict[str, Any]:
    root = cwd.resolve()
    automation_id = (state.get("automation") or {}).get("id")
    # File evidence supplies no host update capability. Use the shared loader.
    if state.get("roadmap_slug"):
        return build_control_plan(root, state["roadmap_slug"], automation_id)
    state_path = Path(state["_state_path"])
    return control_plan_for_readback(state, read_approval_policy(root, state_path, state),
                                     {}, root, automation_id)


PHASE_PROMPT_TERMS = (
    "run the next safe phase-gated delivery step",
    "phase-gated delivery",
    "deliver phase",
    "roadmap delivery",
)

RELEASE_PROMPT_TERMS = (
    "publish",
    "release",
    "promote",
    "promotion",
    "package",
)

COMPLETION_CLAIM_PATTERNS = (
    re.compile(r"\bphase\s+\d+\s+(?:is\s+)?delivered\b", re.IGNORECASE),
    re.compile(r"\bdelivered\s+phase\s+\d+\b", re.IGNORECASE),
)

BROAD_STAGING_PATTERNS = (
    re.compile(r"(?<![\w-])git\s+add\s+(?:\.|-A|--all|--\s+\.|:/|\*)(?:\s|$|&&|;)", re.IGNORECASE),
    re.compile(r"(?<![\w-])git\s+commit\s+(?:-[^\s]*a[^\s]*|--all)(?:\s|$)", re.IGNORECASE),
)

PROTECTED_COMMAND_PATTERNS = (
    (
        re.compile(r"(?<![\w-])git\s+reset\s+--hard\b", re.IGNORECASE),
        "destructive git reset",
    ),
    (
        re.compile(r"(?<![\w-])git\s+clean\s+-[^\n;|&]*[dfx]", re.IGNORECASE),
        "destructive git clean",
    ),
    (
        re.compile(r"(?<![\w-])git\s+checkout\s+--\s+\S+", re.IGNORECASE),
        "destructive git checkout",
    ),
    (
        re.compile(r"(?<![\w-])git\s+restore\b", re.IGNORECASE),
        "destructive git restore",
    ),
    (
        re.compile(r"(?<![\w-])git\s+branch\s+-D\b", re.IGNORECASE),
        "branch deletion",
    ),
    (
        re.compile(r"(?<![\w-])git\s+push\b", re.IGNORECASE),
        "publication or remote mutation",
    ),
    (
        re.compile(r"(?<![\w-])git\s+(?:merge|rebase)\b", re.IGNORECASE),
        "branch promotion or history rewrite",
    ),
    (
        re.compile(r"(?<![\w-])gh\s+release\s+create\b", re.IGNORECASE),
        "release publication",
    ),
    (
        re.compile(r"(?<![\w-])(?:npm|pnpm|yarn)\s+publish\b", re.IGNORECASE),
        "package publication",
    ),
    (
        re.compile(r"(?<![\w-])twine\s+upload\b", re.IGNORECASE),
        "package publication",
    ),
)


def main(argv: List[str]) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    payload = read_hook_input()
    if mode == "guard-bash":
        return guard_bash(payload)
    if mode == "remind-prompt":
        return remind_prompt(payload)
    if mode == "guard-stop":
        return guard_stop(payload)
    return 0


def read_hook_input() -> Dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def emit_json(value: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, sort_keys=True))
    sys.stdout.write("\n")


def guard_bash(payload: Dict[str, Any]) -> int:
    if payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input")
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(command, str) or not command.strip():
        return 0

    for pattern in BROAD_STAGING_PATTERNS:
        if pattern.search(command):
            return ask_pretool(
                "Roadmap Delivery guard: broad git staging can hide unrelated work. "
                "Stage explicit phase-owned paths, or confirm this broad staging command was approved."
            )

    for pattern, label in PROTECTED_COMMAND_PATTERNS:
        if pattern.search(command):
            return ask_pretool(
                "Roadmap Delivery guard: this command looks like "
                f"{label}. Protected operations require explicit human approval and, "
                "for release or publication paths, a completed privacy/release check."
            )

    return 0


def ask_pretool(reason: str) -> int:
    emit_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": reason,
            }
        }
    )
    return 0


def remind_prompt(payload: Dict[str, Any]) -> int:
    prompt = str(payload.get("prompt") or "")
    prompt_lower = prompt.lower()
    cwd = Path(str(payload.get("cwd") or ".")).expanduser()
    states = list(read_delivery_states(cwd))
    contexts: List[str] = []

    for state in states:
        if not prompt_targets_state(prompt_lower, state, states):
            continue
        slug = str(state.get("roadmap_slug") or "roadmap")
        try:
            plan = delivery_plan(cwd, state)
        except (ValueError, RuntimeError, OSError) as exc:
            contexts.append(f"Roadmap Delivery evidence unavailable for {slug}: {exc}. Reconcile before phase work.")
            continue
        if plan["stage"] == "terminal_reconciliation":
            # A prompt-level block would prevent the required alert/pause closeout.
            contexts.append(
                f"Roadmap Delivery hard stop for {slug}: do not start phase work. "
                "Allow terminal closeout; default status-only context authority and explicit opt-outs "
                "use the shared runtime. Load trusted host readback/capability, write the alert "
                f"and verify the receipt. control_plan: {json.dumps(plan, sort_keys=True)}"
            )
        elif plan["stage"] == "blocked_remediation":
            contexts.append(
                f"Blocked Remediation Mode applies before phase delivery for {slug}. "
                "Classify local-repairable, automation-config, permission-gated, "
                "external-decision or destructive-risk; verify the original cause before clearing. "
                f"blocked_reason: {state.get('blocked_reason') or 'not recorded'}. "
                f"control_plan: {json.dumps(plan, sort_keys=True)}"
            )
        elif plan["stage"] == "intentional_activation":
            contexts.append(f"Reconcile manual activation for {slug}: {json.dumps(plan, sort_keys=True)}")

    if any(term in prompt_lower for term in RELEASE_PROMPT_TERMS):
        contexts.append(
            "Roadmap Delivery privacy reminder: publication, promotion, package release, "
            "or credential use requires explicit human approval and the release/privacy checks."
        )

    if contexts:
        emit_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": "\n\n".join(contexts),
                }
            }
        )
    return 0


def guard_stop(payload: Dict[str, Any]) -> int:
    if payload.get("stop_hook_active") is True:
        return 0
    message = str(payload.get("last_assistant_message") or "")
    if not any(pattern.search(message) for pattern in COMPLETION_CLAIM_PATTERNS):
        return 0
    lower = message.lower()
    has_review = "review" in lower and "delivered" in lower
    has_verification = "verification" in lower or "tests" in lower or "passed" in lower
    if has_review and has_verification:
        return 0
    emit_json(
        {
            "decision": "block",
            "reason": (
                "Roadmap Delivery completion guard: before stopping after a delivered-phase "
                "claim, include verification evidence and the delivered review verdict, or keep working."
            ),
        }
    )
    return 0


def read_delivery_states(cwd: Path) -> Iterable[Dict[str, Any]]:
    root = cwd.resolve() if cwd.exists() else Path.cwd()
    automation_root = root / "automation"
    if not automation_root.is_dir():
        return []
    states: List[Dict[str, Any]] = []
    for path in sorted(automation_root.glob("*/delivery_state.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            data["_state_path"] = path.as_posix()
            states.append(data)
    return states


def prompt_targets_state(prompt_lower: str, state: Dict[str, Any], states: List[Dict[str, Any]]) -> bool:
    roadmap = str(state.get("roadmap") or "").lower()
    slug = str(state.get("roadmap_slug") or "").lower()
    if roadmap and roadmap in prompt_lower:
        return True
    if slug and slug in prompt_lower:
        return True
    return len(states) == 1 and any(term in prompt_lower for term in PHASE_PROMPT_TERMS)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
