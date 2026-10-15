"""Durable local operator alerts for roadmap delivery automation."""

from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional

from .paths import resolve_repo_path, slug_forms, state_candidates
from .state import JsonObjectError, atomic_write_text, load_json_object, write_json_object


ALERT_KINDS = {"stalled", "completed", "blocked", "retarget-failed"}
NOTIFICATION_SINKS = {"alert_file", "github_issue", "none", "slack", "email", "codex_thread", "webhook"}
DEFAULT_NEXT_ACTIONS = {
    "stalled": "Inspect the repeated no-progress runs, repair the blocker, or pause the automation.",
    "completed": "Confirm the automation is paused and preserve final verification evidence.",
    "blocked": "Classify the blocker and provide the missing repair, decision, or permission.",
    "retarget-failed": "Retarget the automation to the required next model and rerun readback.",
}


class OperatorAlertError(RuntimeError):
    """Raised when an operator alert cannot be written safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def find_state_file(repo_root: Path, roadmap_slug: str) -> Path:
    forms = slug_forms(roadmap_slug)
    candidates = state_candidates(repo_root, forms)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    checked = ", ".join(str(path) for path in candidates) or "<none>"
    raise OperatorAlertError(f"State file does not exist. Checked: {checked}")


def relative_or_absolute(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def alert_title(kind: str) -> str:
    return kind.replace("-", " ").title()


def safe_filename_timestamp(timestamp: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "-", timestamp).strip("-") or "unknown-time"


def display(value: Any) -> str:
    if value is None or value == "":
        return "not recorded"
    return str(value)


def code_value(value: Any) -> str:
    return f"`{display(value)}`"


def review_summary(state: Dict[str, Any]) -> str:
    review = state.get("last_review")
    if not isinstance(review, dict):
        return "not recorded"
    parts: List[str] = []
    if review.get("file"):
        parts.append(str(review["file"]))
    if review.get("verdict"):
        parts.append(f"verdict {review['verdict']}")
    if review.get("summary"):
        parts.append(str(review["summary"]))
    return " - ".join(parts) if parts else "not recorded"


def verification_summary(state: Dict[str, Any]) -> str:
    verification = state.get("last_verification")
    if not isinstance(verification, dict):
        return "not recorded"
    commands = verification.get("commands") or verification.get("checks")
    if not isinstance(commands, list) or not commands:
        return display(verification.get("summary"))
    fragments: List[str] = []
    for item in commands[:3]:
        if not isinstance(item, dict):
            continue
        command = display(item.get("command"))
        status = display(item.get("status"))
        fragments.append(f"{command}: {status}")
    if len(commands) > 3:
        fragments.append(f"{len(commands) - 3} more command(s)")
    return "; ".join(fragments) if fragments else "not recorded"


def notification_status(sink: str, failure: Optional[str]) -> str:
    if failure:
        return "failed"
    if sink == "alert_file":
        return "local_alert_only"
    if sink == "none":
        return "suppressed"
    return "not_sent"


def build_alert_content(
    repo_root: Path,
    state_file: Path,
    state: Dict[str, Any],
    *,
    kind: str,
    reason: str,
    next_action: str,
    timestamp: str,
    notification_sink: str,
    notification_failure: Optional[str],
) -> str:
    state_dir = state_file.parent
    delivery_log = state_dir / "delivery_log.md"
    review_dir = state_dir / "reviews"
    status = notification_status(notification_sink, notification_failure)
    lines = [
        f"# Roadmap Delivery Alert: {alert_title(kind)}",
        "",
        f"- Alert kind: `{kind}`",
        f"- Created at: `{timestamp}`",
        f"- Roadmap: {code_value(state.get('roadmap'))}",
        f"- Phase: {code_value(state.get('current_phase'))}",
        f"- Status: {code_value(state.get('status'))}",
        f"- Reason: {reason}",
        f"- Required model: {code_value(state.get('required_model'))}",
        f"- Configured model: {code_value(state.get('configured_automation_model'))}",
        f"- Required reasoning effort: {code_value(state.get('required_reasoning_effort'))}",
        f"- Configured reasoning effort: {code_value(state.get('configured_automation_reasoning_effort'))}",
        f"- Last verification: {verification_summary(state)}",
        f"- Last review: {review_summary(state)}",
        f"- State file: `{relative_or_absolute(repo_root, state_file)}`",
        f"- Delivery log: `{relative_or_absolute(repo_root, delivery_log)}`",
        f"- Review directory: `{relative_or_absolute(repo_root, review_dir)}`",
        f"- Notification sink: `{notification_sink}`",
        f"- Notification status: `{status}`",
        f"- Next human action: {next_action}",
    ]
    if notification_failure:
        lines.append(f"- Notification failure: {notification_failure}")
    lines.extend(
        [
            "",
            "Local alert file is the durable fallback. External notification sinks are optional and must not remove this file on failure.",
            "",
        ]
    )
    return "\n".join(lines)


def append_delivery_log(
    delivery_log: Path,
    *,
    kind: str,
    timestamp: str,
    alert_file: str,
    reason: str,
    notification_sink: str,
    status: str,
    notification_failure: Optional[str],
) -> None:
    lines = [
        "",
        f"## Operator Alert - {timestamp} - {alert_title(kind)}",
        "",
        f"- Alert file: `{alert_file}`",
        f"- Reason: {reason}",
        f"- Notification sink: `{notification_sink}`",
        f"- Notification status: `{status}`",
    ]
    if notification_failure:
        lines.append(f"- Notification failure: {notification_failure}")
    lines.append("")
    try:
        with delivery_log.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    except OSError as exc:
        raise OperatorAlertError(f"Cannot append delivery log {delivery_log}: {exc}") from exc


def ensure_terminal_alert(repo_root: Path, state_file: Path, state: Dict[str, Any],
                          closeout: Dict[str, Any]) -> None:
    """Idempotent local effect. The closeout journal persists alert metadata.

    A deterministic path recovers a crash after file creation but before state
    recording without inventing a second alert or external notification.
    """
    kind = "completed" if closeout["context"] == "completion" else "stalled"
    alerts = state_file.parent / "alerts"
    alerts.mkdir(parents=True, exist_ok=True)
    path = alerts / f"terminal-{closeout['intent_id']}-{kind}.md"
    reason = "All phases complete; reconcile final evidence and scheduler pause." if kind == "completed" else state.get("blocked_reason") or "Consecutive no-progress threshold reached."
    content = build_alert_content(repo_root, state_file, state, kind=kind, reason=reason,
                                  next_action=DEFAULT_NEXT_ACTIONS[kind], timestamp=closeout["created_at"],
                                  notification_sink="alert_file", notification_failure=None)
    required = ("Alert kind:", "State file:", "Delivery log:", "Next human action:")
    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    except (OSError, UnicodeError) as exc:
        existing = ""
        closeout["alert_recovery_diagnostic"] = f"Cannot read terminal alert; replacing owned artifact: {exc}"
    if not all(marker in existing for marker in required):
        atomic_write_text(path, content)
    state["last_operator_alert"] = {"kind": kind, "file": relative_or_absolute(repo_root, path),
                                    "timestamp": closeout["created_at"], "reason": reason,
                                    "next_human_action": DEFAULT_NEXT_ACTIONS[kind],
                                    "notification_sink": "alert_file", "notification_status": "local_alert_only"}


def write_alert(
    repo_root: Path,
    state_file: Path,
    *,
    kind: str,
    reason: str,
    next_action: Optional[str] = None,
    timestamp: Optional[str] = None,
    notification_sink: str = "alert_file",
    notification_failure: Optional[str] = None,
) -> Dict[str, Any]:
    if kind not in ALERT_KINDS:
        raise OperatorAlertError(f"Unsupported alert kind {kind!r}. Expected one of {sorted(ALERT_KINDS)}.")
    if notification_sink not in NOTIFICATION_SINKS:
        raise OperatorAlertError(f"Unsupported notification sink {notification_sink!r}.")

    timestamp = timestamp or utc_now()
    next_action = next_action or DEFAULT_NEXT_ACTIONS[kind]
    try:
        state = load_json_object(state_file)
    except JsonObjectError as exc:
        raise OperatorAlertError(str(exc)) from exc

    alerts_dir = state_file.parent / "alerts"
    alerts_dir.mkdir(parents=True, exist_ok=True)
    alert_path = alerts_dir / f"{safe_filename_timestamp(timestamp)}-{kind}.md"
    content = build_alert_content(
        repo_root,
        state_file,
        state,
        kind=kind,
        reason=reason,
        next_action=next_action,
        timestamp=timestamp,
        notification_sink=notification_sink,
        notification_failure=notification_failure,
    )
    try:
        alert_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise OperatorAlertError(f"Cannot write alert file {alert_path}: {exc}") from exc

    relative_alert = relative_or_absolute(repo_root, alert_path)
    status = notification_status(notification_sink, notification_failure)
    state["last_operator_alert"] = {
        "kind": kind,
        "file": relative_alert,
        "timestamp": timestamp,
        "reason": reason,
        "next_human_action": next_action,
        "notification_sink": notification_sink,
        "notification_status": status,
    }
    if notification_failure:
        state["last_operator_alert"]["notification_failure"] = notification_failure
    state["updated_at"] = timestamp
    try:
        write_json_object(state_file, state)
    except JsonObjectError as exc:
        raise OperatorAlertError(str(exc)) from exc

    append_delivery_log(
        state_file.parent / "delivery_log.md",
        kind=kind,
        timestamp=timestamp,
        alert_file=relative_alert,
        reason=reason,
        notification_sink=notification_sink,
        status=status,
        notification_failure=notification_failure,
    )

    return {
        "kind": kind,
        "alert_file": str(alert_path),
        "alert_file_relative": relative_alert,
        "timestamp": timestamp,
        "notification_sink": notification_sink,
        "notification_status": status,
        "notification_failure": notification_failure,
        "state_file": str(state_file),
        "delivery_log": str(state_file.parent / "delivery_log.md"),
    }


def print_text(result: Dict[str, Any]) -> None:
    for key in (
        "kind",
        "alert_file",
        "timestamp",
        "notification_sink",
        "notification_status",
        "state_file",
        "delivery_log",
    ):
        print(f"{key}: {result.get(key)}")
    if result.get("notification_failure"):
        print(f"notification_failure: {result['notification_failure']}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Write a durable local operator alert for roadmap delivery automation.")
    parser.add_argument("--repo-root", required=True, help="Repository root.")
    parser.add_argument("--roadmap-slug", help="Roadmap slug, accepting hyphen or underscore form.")
    parser.add_argument("--state-file", help="Explicit delivery_state.json path.")
    parser.add_argument("--kind", required=True, choices=sorted(ALERT_KINDS), help="Alert kind to write.")
    parser.add_argument("--reason", required=True, help="Operator-facing reason for the alert.")
    parser.add_argument("--next-action", help="Next human action to include in the alert.")
    parser.add_argument("--timestamp", help="Timestamp to write, mainly for deterministic tests.")
    parser.add_argument("--notification-sink", default="alert_file", choices=sorted(NOTIFICATION_SINKS))
    parser.add_argument("--notification-failure", help="Optional external notification failure to record.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).expanduser().resolve()
    if args.state_file:
        state_file = Path(args.state_file).expanduser()
        if not state_file.is_absolute():
            state_file = repo_root / state_file
    elif args.roadmap_slug:
        try:
            state_file = find_state_file(repo_root, args.roadmap_slug)
        except OperatorAlertError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    else:
        parser.error("one of --roadmap-slug or --state-file is required")

    try:
        result = write_alert(
            repo_root,
            state_file,
            kind=args.kind,
            reason=args.reason,
            next_action=args.next_action,
            timestamp=args.timestamp,
            notification_sink=args.notification_sink,
            notification_failure=args.notification_failure,
        )
    except OperatorAlertError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print_text(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
