"""Narrow runner updates and durable, resumable terminal reconciliation.

Host adapters provide acknowledged readback and an idempotent status-only
operation. Local TOML is never assumed to be a scheduler's source of truth.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Protocol

from .state import JsonObjectError, atomic_write_text, load_json_object, review_verdict, write_json_object
from .toml import TomlError, dump_toml, parse_minimal_toml, parse_toml


DEFAULT_AUTOMATIONS_DIR = Path.home() / ".codex" / "automations"
AUTOMATIONS_DIR_ENV = "AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR"
# This transport timestamp is set by the host, not a runner setting.
TRANSPORT_FIELDS = {"updated_at"}


class AutomationConfigError(RuntimeError):
    """Raised when a saved automation config cannot be read or updated."""


class RunnerError(AutomationConfigError):
    def __init__(self, code: str, message: str, *, transient: bool = False):
        super().__init__(message)
        self.code = code
        self.transient = transient


class RunnerAdapter(Protocol):
    """Readback must be authoritative; updates must compare the revision.

    Reusing request_id must be idempotent. An update acknowledgement by itself
    is never evidence of PAUSED. Full-payload adapters preserve unknown fields.
    """
    def readback(self, automation_id: str) -> Dict[str, Any]: ...
    def pause_status_only(self, request: Dict[str, Any]) -> None: ...


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def automations_dir(path: Optional[Path] = None) -> Path:
    return (path if path is not None else Path(os.environ.get(AUTOMATIONS_DIR_ENV, str(DEFAULT_AUTOMATIONS_DIR)))).expanduser()


def automation_config_path(automation_id: str, *, root: Optional[Path] = None) -> Path:
    if not automation_id or automation_id in {".", ".."} or any(c in automation_id for c in ("/", "\\", "\x00")):
        raise AutomationConfigError("Automation id must be a single directory name.")
    return automations_dir(root) / automation_id / "automation.toml"


def read_automation_config(path: Path) -> Dict[str, Any]:
    try:
        return parse_minimal_toml(path)
    except (OSError, TomlError) as exc:
        raise AutomationConfigError(f"Cannot read automation config {path}: {exc}") from exc


def _replace_status(text: str, status: str) -> str:
    data = parse_toml(text)
    if data.get("status") not in {"ACTIVE", "PAUSED"} or status != "PAUSED":
        raise AutomationConfigError("A known top-level status and a PAUSED target are required.")
    return dump_toml({**data, "status": status})


def config_revision(config: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, default=lambda value: {"$type": type(value).__name__, "value": str(value)}, ensure_ascii=False).encode()).hexdigest()


def runner_snapshot(config: Dict[str, Any], *, source: str, authoritative: bool = True,
                    revision: Optional[str] = None) -> Dict[str, Any]:
    return {"config": deepcopy(config), "revision": revision or config_revision(config),
            "source": source, "scheduler_authoritative": authoritative}


def validate_runner_snapshot(snapshot: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    if (not isinstance(snapshot, dict) or not isinstance(snapshot.get("config"), dict)
            or snapshot.get("scheduler_authoritative") is not True
            or not isinstance(snapshot.get("source"), str) or not snapshot["source"]
            or not isinstance(snapshot.get("revision"), str) or not snapshot["revision"]):
        raise RunnerError("unsupported", "Authoritative runner readback with a revision is required.")
    config = snapshot["config"]
    if (not isinstance(expected, dict) or not expected.get("id")
            or config.get("id") != expected["id"]
            or any(config.get(key) != value for key, value in expected.items())):
        raise RunnerError("identity_mismatch", "Runner identity/scope differs from the selected automation.")
    if config.get("status") not in {"ACTIVE", "PAUSED"}:
        raise RunnerError("readback_unknown", "Runner has no recognized ACTIVE/PAUSED status.")
    return deepcopy(config)


def _settings(config: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in config.items() if key not in TRANSPORT_FIELDS | {"status"}}


def prepare_pause_request(snapshot: Dict[str, Any], expected: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    config = validate_runner_snapshot(snapshot, expected)
    if not isinstance(request_id, str) or not request_id:
        raise RunnerError("invalid_input", "A durable request id is required.")
    return {"schema_version": 1, "operation": "pause_status_only", "runner_id": config["id"],
            "request_id": request_id, "expected_revision": snapshot["revision"],
            "preserve_non_status_settings": True,
            "settings_sha256": config_revision(_settings(config)),
            "payload": {**config, "status": "PAUSED"},
            "required_tool": "host supported status update followed by authoritative readback"}


def validate_pause_request(request: Dict[str, Any], runner_id: str, request_id: Optional[str] = None) -> None:
    """Bind the full outgoing payload before any adapter can execute it."""
    if (not isinstance(request, dict) or request.get("schema_version") != 1
            or request.get("operation") != "pause_status_only"
            or request.get("runner_id") != runner_id
            or not isinstance(request.get("request_id"), str) or not request["request_id"]
            or (request_id is not None and request["request_id"] != request_id)
            or not isinstance(request.get("expected_revision"), str) or not request["expected_revision"]
            or request.get("preserve_non_status_settings") is not True
            or not isinstance(request.get("payload"), dict)
            or request["payload"].get("id") != runner_id or request["payload"].get("status") != "PAUSED"
            or config_revision(_settings(request["payload"])) != request.get("settings_sha256")):
        raise RunnerError("invalid_request", "Stored pause request/payload does not match its identity and settings binding.")


def verify_pause_receipt(snapshot: Dict[str, Any], expected: Dict[str, Any], request: Dict[str, Any]) -> Dict[str, Any]:
    validate_pause_request(request, expected["id"])
    config = validate_runner_snapshot(snapshot, expected)
    if config_revision(_settings(config)) != request["settings_sha256"]:
        raise RunnerError("settings_changed", "Runner settings changed across the status-only update; reconcile before continuing.")
    if config["status"] != "PAUSED":
        raise RunnerError("pause_unconfirmed", "Pause request did not read back PAUSED.", transient=True)
    return {"status": "paused", "paused": True, "readback_status": "PAUSED",
            "runner_id": config["id"], "request_id": request["request_id"],
            "observed_revision": snapshot["revision"], "source": snapshot["source"],
            "scheduler_authoritative": True, "settings_sha256": request["settings_sha256"]}


class FileRunnerAdapter:
    """Opt-in backend only for hosts documenting this file as authoritative.

    The contract string is an operator-supplied host capability reference, not
    proof that Codex reads config changes as live scheduler acknowledgements.
    Atomic updates and advisory locks require cooperating writers. A final
    byte revision check rejects changes made since the observed snapshot.
    """
    def __init__(self, root: Path, *, host_contract: Optional[str] = None):
        self.root = root
        self.host_contract = host_contract

    def _path(self, automation_id: str) -> Path:
        if not self.host_contract:
            raise RunnerError("unsupported", "File backend requires a documented authoritative host contract; use the host tool.")
        path = automation_config_path(automation_id, root=self.root)
        if path.is_symlink() or path.parent.is_symlink():
            raise RunnerError("unsafe_path", "Runner config must not be a symlink.")
        return path

    def readback(self, automation_id: str) -> Dict[str, Any]:
        path = self._path(automation_id)
        try:
            raw = path.read_bytes()
            config = parse_toml(raw.decode("utf-8"))
        except (OSError, ValueError) as exc:
            raise RunnerError("read_failed", str(exc)) from exc
        return runner_snapshot(config, source=self.host_contract,
                               revision=hashlib.sha256(raw).hexdigest())

    def pause_status_only(self, request: Dict[str, Any]) -> None:
        validate_pause_request(request, request.get("runner_id"))
        path = self._path(request["runner_id"])
        from .progress import _recording_lock
        with _recording_lock(path):
            current = self.readback(request["runner_id"])
            if current["revision"] != request["expected_revision"]:
                # A replay may find the prior update already persisted.
                if current["config"].get("status") != "PAUSED":
                    raise RunnerError("stale_revision", "Runner changed since observed revision.")
                verify_pause_receipt(current, {"id": request["runner_id"]}, request)
                return
            if config_revision(_settings(current["config"])) != request["settings_sha256"]:
                raise RunnerError("settings_changed", "Request does not match the observed runner settings.")
            if path.stat().st_mode & 0o222 == 0 or path.parent.stat().st_mode & 0o222 == 0:
                raise RunnerError("write_failed", "Runner configuration is read-only.")
            candidate = _replace_status(path.read_text(encoding="utf-8"), "PAUSED")
            if parse_toml(candidate) != {**current["config"], "status": "PAUSED"}:
                raise RunnerError("invalid_candidate", "Candidate changed unrelated configuration values.")
            if hashlib.sha256(path.read_bytes()).hexdigest() != current["revision"]:
                raise RunnerError("stale_revision", "Runner changed before replacement.")
            try:
                atomic_write_text(path, candidate)
            except JsonObjectError as exc:
                raise RunnerError("write_failed", str(exc)) from exc


def pause_saved_automation(automation_id: Optional[str], *, root: Optional[Path] = None,
                           timestamp: Optional[str] = None, reason: Optional[str] = None,
                           host_contract: Optional[str] = None,
                           adapter: Optional[RunnerAdapter] = None,
                           expected: Optional[Dict[str, Any]] = None,
                           expected_revision: Optional[str] = None,
                           request_id: str = "status-only-pause") -> Dict[str, Any]:
    """Compatibility entrypoint. File mutation requires an explicit host contract.

    The caller owns authorization; terminal workflows use resume_terminal_closeout
    to resolve policy and durably record intent before invoking an effect.
    """
    result = {"automation_id": automation_id, "attempted": False, "paused": False,
              "status": "missing_automation_id", "paused_at": timestamp or utc_now(), "reason": reason}
    if not automation_id:
        return result
    backend = adapter or FileRunnerAdapter(automations_dir(root), host_contract=host_contract)
    expected = expected or {"id": automation_id}
    try:
        if expected.get("id") != automation_id:
            raise RunnerError("identity_mismatch", "Expected runner differs from selected automation id.")
        initial = backend.readback(automation_id)
        config = validate_runner_snapshot(initial, expected)
        if expected_revision is not None and initial["revision"] != expected_revision:
            raise RunnerError("stale_revision", "Observed runner revision changed before pause.")
        result["previous_status"] = config["status"]
        request = prepare_pause_request(initial, expected, request_id)
        if config["status"] != "PAUSED":
            result["attempted"] = True
            if not callable(getattr(backend, "pause_status_only", None)):
                raise RunnerError("unsupported", "Adapter has no supported status-only update operation.")
            backend.pause_status_only(request)
        receipt = verify_pause_receipt(backend.readback(automation_id), expected, request)
        result.update(receipt)
        if not result["attempted"]:
            result["status"] = "already_paused"
    except RunnerError as exc:
        result.update(status=exc.code, reason=str(exc))
    except (OSError, AutomationConfigError, JsonObjectError) as exc:
        result.update(status="update_failed", reason=str(exc))
    return result


def automation_id_from_state(state: Dict[str, Any]) -> Optional[str]:
    automation = state.get("automation")
    if isinstance(automation, dict) and automation.get("id"):
        return str(automation["id"])
    return str(state["automation_id"]) if state.get("automation_id") else None


def _closeout_context(state: Dict[str, Any]) -> Optional[str]:
    if state.get("all_phases_complete") is True or state.get("status") in {"completed", "completed_pending_pause"}:
        return "completion"
    count, threshold = state.get("stalled_run_count", 0), state.get("max_stalled_runs", 2)
    if type(count) is not int or type(threshold) is not int or count < 0 or threshold < 1:
        raise RunnerError("invalid_input", "Malformed consecutive-run counters.")
    return "stall" if count >= threshold else None


def _terminal_evidence(repo_root: Path, state: Dict[str, Any]) -> Dict[str, Any]:
    diagnostics = []
    def exists(value: Any) -> bool:
        try:
            return isinstance(value, str) and bool(value) and (repo_root / value).is_file()
        except OSError as exc:
            diagnostics.append(f"Cannot inspect final evidence {value}: {exc}")
            return False
    verification, review = state.get("last_verification"), state.get("last_review")
    verification = verification if isinstance(verification, dict) else {}
    review = review if isinstance(review, dict) else {}
    review_file = repo_root / review["file"] if exists(review.get("file")) else None
    review_delivered = False
    if review_file is not None:
        try:
            review_delivered = review_verdict(review_file.read_text(encoding="utf-8")) == "delivered"
            if not review_delivered:
                diagnostics.append("Final review must contain one unambiguous delivered verdict.")
        except (OSError, UnicodeError) as exc:
            diagnostics.append(f"Cannot read final review {review_file}: {exc}")
    waiver_reason = state.get("final_deep_review_waiver_reason")
    return {"diagnostics": diagnostics,
            "final_verification_passed": verification.get("status") == "passed" and exists(verification.get("output_file")),
            "delivered_review": review.get("verdict") == "delivered" and review_delivered,
            "final_deep_review_prompt_present": state.get("final_deep_review_prompt_prepared") is True and exists(state.get("final_deep_review_prompt_file"))
                                               and (repo_root / state["final_deep_review_prompt_file"]).resolve() != (repo_root / (review.get("file") or "")).resolve(),
            "human_waiver_recorded": state.get("final_deep_review_status") == "waived-by-human" and isinstance(waiver_reason, str) and bool(waiver_reason.strip())}


def _validate_closeout(closeout: Dict[str, Any], intent_id: str, context: str, runner_id: Optional[str]) -> None:
    if (not isinstance(closeout, dict) or closeout.get("schema_version") != 1
            or closeout.get("intent_id") != intent_id or closeout.get("context") != context
            or closeout.get("runner_id") != runner_id
            or type(closeout.get("attempts")) is not int or closeout["attempts"] < 0
            or type(closeout.get("max_attempts")) is not int or not 1 <= closeout["max_attempts"] <= 3
            or closeout["attempts"] > closeout["max_attempts"]
            or not isinstance(closeout.get("created_at"), str)
            or not isinstance(closeout.get("status"), str)
            or "receipt" not in closeout or "request" not in closeout):
        raise RunnerError("invalid_journal", "Terminal intent counters/identity are malformed; preserve and reconcile it.")
    if closeout["request"] is not None:
        validate_pause_request(closeout["request"], runner_id, intent_id)
    if closeout.get("attempt_transport") not in {None, "external", "adapter"}:
        raise RunnerError("invalid_journal", "Unknown terminal attempt transport.")
    rejection = closeout.get("effect_rejection")
    if rejection is not None and (not isinstance(rejection, dict)
            or not isinstance(rejection.get("code"), str) or not rejection["code"]
            or not isinstance(rejection.get("reason"), str) or not rejection["reason"]):
        raise RunnerError("invalid_journal", "Invalid durable effect rejection.")
    outcomes = closeout.get("external_outcomes", [])
    if not isinstance(outcomes, list):
        raise RunnerError("invalid_journal", "External outcome history must be a list.")
    attempts = []
    for outcome in outcomes:
        _validate_external_outcome(outcome, closeout)
        attempts.append(outcome["attempt"])
    if len(attempts) != len(set(attempts)):
        raise RunnerError("invalid_journal", "External attempt outcomes must be unique.")


def _validate_external_outcome(outcome: Any, closeout: Dict[str, Any]) -> None:
    if (not isinstance(outcome, dict)
            or set(outcome) != {"request_id", "attempt", "status", "source"}
            or outcome.get("request_id") != closeout["intent_id"]
            or type(outcome.get("attempt")) is not int
            or not 1 <= outcome["attempt"] <= closeout["attempts"]
            or outcome.get("status") not in {"acknowledged", "transient_failure", "permission_required", "unsupported", "not_executed"}
            or not isinstance(outcome.get("source"), str) or not outcome["source"].strip()
            or closeout.get("request") is None):
        raise RunnerError("invalid_external_outcome", "Bind a host outcome to its exact request, reserved attempt, status and source.")


def resume_terminal_closeout(repo_root: Path, state_file: Path, *,
                              adapter: Optional[RunnerAdapter] = None,
                              observed: Optional[Dict[str, Any]] = None,
                              external_outcome: Optional[Dict[str, Any]] = None,
                              max_attempts: int = 2,
                              timestamp: Optional[str] = None,
                              failpoint: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """Resume terminal effects only; allocate no phase attempt or run counter.

    Without a Python host adapter, emit an action request for the agent's host
    tool once per reserved attempt. A later invocation supplies its bound outcome
    and fresh authoritative readback. Inspection cannot reissue an outstanding
    action; acknowledgements alone cannot complete closeout. Retries are persisted and
    bounded, including attempts interrupted after intent and before invocation.
    """
    from .alerts import OperatorAlertError, ensure_terminal_alert
    from .approval import read_approval_policy
    from .control import decide_control
    from .progress import _recording_lock

    if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
        raise RunnerError("invalid_input", "Retry bound must be between one and three.")
    try:
        state_file.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise RunnerError("unsafe_path", "Terminal state must be inside the selected repository.") from exc
    if state_file.is_symlink():
        raise RunnerError("unsafe_path", "Terminal state must not be a symlink.")
    stamp = timestamp or utc_now()
    hook = failpoint or (lambda point: None)
    with _recording_lock(state_file):
        state = load_json_object(state_file)
        context = _closeout_context(state)
        if context is None:
            return {"result": "not_applicable", "status": "nonterminal", "extract_phase": False, "exit_code": 0}
        runner_id = automation_id_from_state(state)
        automation = state.get("automation") or {}
        manual = automation.get("kind") == "manual" or state.get("execution_environment") == "manual"
        expected = {"id": runner_id} if runner_id else {}
        # State supplies scope; readback alone cannot authorize another project.
        if automation.get("project_id"):
            expected["target"] = {"type": "project", "project_id": automation["project_id"]}
        if not manual:
            expected["cwds"] = [automation.get("cwd") or str(repo_root.resolve())]
        if automation.get("execution_environment"):
            expected["execution_environment"] = automation["execution_environment"]
        intent_id = config_revision({"roadmap": state.get("roadmap_slug"), "context": context,
                                     "runner_id": runner_id, "epoch": state.get("last_completed_run_id")})[:24]
        journal = state_file.parent / "terminal_closeout.json"
        if journal.is_symlink():
            raise RunnerError("unsafe_path", "Terminal journal must not be a symlink.")
        if journal.exists():
            saved = load_json_object(journal)
            if saved.get("schema_version") != 1 or not isinstance(saved.get("intent_id"), str):
                raise RunnerError("invalid_journal", "Invalid terminal journal envelope.")
            if saved.get("intent_id") == intent_id:
                changes = saved.get("state_changes")
                if not isinstance(changes, dict) or not isinstance(changes.get("terminal_closeout"), dict):
                    raise RunnerError("invalid_journal", "Terminal journal is malformed; preserve and reconcile it.")
                allowed = {"status", "updated_at", "terminal_closeout", "last_operator_alert", "last_automation_pause", "configured_automation_status", "automation"}
                if set(changes) - allowed or changes.get("status") not in {"blocked", "completed", "completed_pending_pause"}:
                    raise RunnerError("invalid_journal", "Terminal journal contains unrelated state changes.")
                if "automation" in changes:
                    old_scope = {k:v for k,v in automation.items() if k != "status"}
                    recovered = changes["automation"] or {}
                    if not isinstance(recovered, dict) or {k:v for k,v in recovered.items() if k != "status"} != old_scope:
                        raise RunnerError("invalid_journal", "Terminal journal changes runner scope.")
                _validate_closeout(changes["terminal_closeout"], intent_id, context, runner_id)
                state.update(deepcopy(changes))
        closeout = state.get("terminal_closeout")
        if not isinstance(closeout, dict) or closeout.get("intent_id") != intent_id:
            closeout = {"schema_version": 1, "intent_id": intent_id, "context": context,
                        "runner_id": runner_id, "created_at": stamp, "attempts": 0,
                        "max_attempts": max_attempts, "status": "intent_recorded", "request": None,
                        "receipt": None, "required_action": None}
        _validate_closeout(closeout, intent_id, context, runner_id)
        previous_receipt = deepcopy(closeout.get("receipt"))
        if closeout["attempts"] and closeout.get("request") and closeout.get("attempt_transport") is None:
            # Legacy reservations lack transport provenance; require an outcome
            # or PAUSED proof rather than guessing that another execution is safe.
            closeout["attempt_transport"] = "external"
        if external_outcome is not None:
            _validate_external_outcome(external_outcome, closeout)
            outcomes = closeout.setdefault("external_outcomes", [])
            previous = next((item for item in outcomes if item["attempt"] == external_outcome["attempt"]), None)
            if previous is not None and previous != external_outcome:
                raise RunnerError("invalid_external_outcome", "An attempt already has a different outcome; preserve its history.")
            if previous is None:
                if (external_outcome["attempt"] != closeout["attempts"]
                        or closeout.get("attempt_transport") != "external"):
                    raise RunnerError("invalid_external_outcome", "Only the current outstanding attempt can receive a new outcome.")
                outcomes.append(deepcopy(external_outcome))
                status = external_outcome["status"]
                closeout.update(status="pause_unconfirmed" if status == "acknowledged" else
                                "transient_failure" if status == "not_executed" else status,
                                transient=status in {"transient_failure", "not_executed"},
                                required_action="Host outcome recorded; verify fresh scheduler readback.")
                if status in {"permission_required", "unsupported"}:
                    closeout["effect_rejection"] = {"code": status,
                        "reason": f"Host rejected terminal attempt: {status}. Reconcile manually; do not retry the effect."}
        action_emitted = False
        state["terminal_closeout"] = closeout
        state["status"] = "completed_pending_pause" if context == "completion" else "blocked"

        def checkpoint(point: str) -> None:
            state["updated_at"] = stamp
            changes = {key: deepcopy(state[key]) for key in
                       ("status", "updated_at", "terminal_closeout", "last_operator_alert", "last_automation_pause",
                        "configured_automation_status", "automation") if key in state}
            write_json_object(journal, {"schema_version": 1, "intent_id": intent_id, "state_changes": changes})
            hook("after_journal_" + point)
            write_json_object(state_file, state)
            hook("after_state_" + point)

        checkpoint("intent")
        hook("before_alert")
        alert_error = None
        try:
            ensure_terminal_alert(repo_root, state_file, state, closeout)
        except (OSError, UnicodeError, JsonObjectError, OperatorAlertError) as exc:
            alert_error = f"Restore terminal alert evidence: {exc}"
        closeout["alert_error"] = alert_error
        hook("after_alert")
        checkpoint("alert")
        policy = read_approval_policy(repo_root, state_file, state)
        evidence = _terminal_evidence(repo_root, state) if context == "completion" else {}
        closeout["evidence_diagnostics"] = evidence.get("diagnostics", [])
        snapshot = observed
        read_error = None
        authority = policy.get("execution_valid") is not False
        # Do not contact the runner at all for explicit context opt-outs/manual.
        from .approval import approval_decision_for_pause_context
        disabled = approval_decision_for_pause_context(policy, context).get("decision") == "disabled"
        if adapter is not None and not manual and not disabled and authority:
            try:
                hook("before_readback")
                if not callable(getattr(adapter, "readback", None)):
                    raise RunnerError("unsupported", "Adapter has no supported runner readback operation.")
                snapshot = adapter.readback(runner_id)
                hook("after_readback")
            except RunnerError as exc:
                read_error = exc
            except OSError as exc:
                read_error = RunnerError("transient_failure", str(exc), transient=True)
        config = {}
        if snapshot is not None and not disabled and not manual:
            try:
                config = validate_runner_snapshot(snapshot, expected)
                try:
                    json.dumps(snapshot)
                except (TypeError, ValueError) as exc:
                    raise RunnerError("unsupported", "Terminal host snapshots must contain JSON-compatible configuration values.") from exc
                closeout["last_readback"] = deepcopy(snapshot)
            except RunnerError as exc:
                read_error = exc
        normalized_expected = {"id": runner_id}
        normalized_observed = {"id": config.get("id"), "status": config.get("status")}
        plan = decide_control(state, policy, evidence,
                              {"kind": "manual" if manual else "scheduled",
                               "expected": normalized_expected, "observed": normalized_observed,
                               "capabilities": {"readback": bool(config) and read_error is None,
                                                "status_update": callable(getattr(adapter, "pause_status_only", None)) if adapter is not None else observed is not None}})
        if config:
            state["configured_automation_status"] = config["status"]
            if isinstance(state.get("automation"), dict):
                state["automation"]["status"] = config["status"]
        if read_error is not None:
            closeout.update(status=read_error.code, required_action=str(read_error), receipt=None)
            closeout["last_readback_error"] = {"code": read_error.code, "reason": str(read_error)}
            if closeout.get("effect_rejection"):
                closeout["required_action"] += " " + closeout["effect_rejection"]["reason"]
        elif plan["action"] == "record_not_applicable":
            closeout.update(status="not_applicable", receipt=None, required_action=None)
        elif plan["result"] == "disabled":
            closeout.update(status="disabled", receipt=None,
                            required_action="Automatic terminal pause explicitly disabled; pause manually if desired.")
        elif plan["result"] in {"invalid_input", "permission_required", "unsupported"}:
            closeout.update(status=plan["result"], receipt=None,
                            required_action="Provide supported runner readback/status update for the selected identity: " + plan["reason_code"])
        else:
            request = closeout.get("request")
            effect_invoked = False
            try:
                if request is not None:
                    validate_pause_request(request, runner_id, intent_id)
                if request is not None and config_revision(_settings(config)) != request["settings_sha256"]:
                    raise RunnerError("settings_changed", "Runner settings changed since terminal intent; reconcile manually.")
                if request is None:
                    request = prepare_pause_request(snapshot, expected, intent_id)
                    closeout["request"] = request
                if config.get("status") == "PAUSED":
                    receipt = verify_pause_receipt(snapshot, expected, request)
                    if closeout["attempts"] == 0:
                        receipt["status"] = "already_paused"
                    closeout.update(status=receipt["status"], receipt=receipt, required_action=None)
                elif previous_receipt:
                    closeout["previous_receipt"] = previous_receipt
                    raise RunnerError("runner_reactivated", "Runner reads ACTIVE after a confirmed terminal pause; pause it through the supported host tool and provide fresh readback.")
                elif closeout.get("effect_rejection"):
                    rejection = closeout["effect_rejection"]
                    raise RunnerError(rejection["code"], rejection["reason"])
                elif (closeout.get("attempt_transport") == "external" and closeout["attempts"] > 0
                      and not any(item["attempt"] == closeout["attempts"] for item in closeout.get("external_outcomes", []))):
                    # An outstanding reservation is not another execution grant.
                    closeout.update(status="pause_requested", required_action=
                                    "Record the outstanding host attempt outcome and fresh readback; do not execute its request again.")
                elif closeout["attempts"] > 0 and closeout["status"] not in {"pause_requested", "pause_unconfirmed", "transient_failure"} and not closeout.get("transient"):
                    raise RunnerError(closeout["status"], closeout.get("required_action") or "Reconcile rejected terminal request manually.")
                elif closeout["attempts"] >= closeout["max_attempts"]:
                    raise RunnerError("retry_exhausted", "Bounded pause retries exhausted; pause selected automation through its supported host tool, then provide fresh readback.")
                elif request["expected_revision"] != snapshot["revision"]:
                    raise RunnerError("stale_revision", "Runner revision changed before update; reconcile manually.")
                else:
                    closeout["attempts"] += 1
                    closeout["attempt_transport"] = "external" if adapter is None else "adapter"
                    closeout.update(status="pause_requested", required_action="Execute stored status-only action and supply authoritative PAUSED readback.")
                    checkpoint("request")
                    hook("before_pause")
                    action_emitted = adapter is None
                    if adapter is not None:
                        effect_invoked = True
                        adapter.pause_status_only(deepcopy(request))
                        hook("after_pause")
                        hook("before_receipt_readback")
                        snapshot = adapter.readback(runner_id)
                        config = validate_runner_snapshot(snapshot, expected)
                        try:
                            json.dumps(snapshot)
                        except (TypeError, ValueError) as exc:
                            raise RunnerError("unsupported", "Terminal readback contains values incompatible with its durable JSON journal.") from exc
                        closeout["last_readback"] = deepcopy(snapshot)
                        receipt = verify_pause_receipt(snapshot, expected, request)
                        hook("after_receipt_readback")
                        closeout.update(status=receipt["status"], receipt=receipt, required_action=None)
            except RunnerError as exc:
                closeout.update(status=exc.code, receipt=None, required_action=str(exc), transient=exc.transient)
                if effect_invoked and not exc.transient and exc.code != "pause_unconfirmed":
                    closeout["effect_rejection"] = {"code": exc.code, "reason": str(exc)}
            except OSError as exc:
                closeout.update(status="transient_failure", receipt=None, required_action=str(exc), transient=True)
        if config:
            state["configured_automation_status"] = config["status"]
            if isinstance(state.get("automation"), dict):
                state["automation"]["status"] = config["status"]
        if not closeout.get("receipt"):
            if previous_receipt:
                closeout["previous_receipt"] = previous_receipt
            state["last_automation_pause"] = {"status": closeout["status"], "paused": False,
                                             "readback_status": config.get("status"), "context": context,
                                             "reason": closeout.get("required_action"), "observed_at": stamp}
        if closeout.get("receipt"):
            state["last_automation_pause"] = {**deepcopy(closeout["receipt"]), "paused_at": stamp, "context": context}
            state["configured_automation_status"] = "PAUSED"
            if isinstance(state.get("automation"), dict):
                state["automation"]["status"] = "PAUSED"
        final_gates = not alert_error and evidence.get("final_verification_passed") and evidence.get("delivered_review") and (evidence.get("final_deep_review_prompt_present") or evidence.get("human_waiver_recorded"))
        if context == "completion" and final_gates and (closeout.get("receipt") or closeout["status"] == "not_applicable"):
            state["status"] = "completed"
        if context == "completion" and not final_gates:
            final_action = "Supply final verification, delivered review and distinct final deep-review prompt or recorded human waiver."
            closeout["required_action"] = ((closeout.get("required_action") + " ") if closeout.get("required_action") else "Preserve pause outcome; ") + final_action
        if alert_error:
            closeout["required_action"] = ((closeout.get("required_action") + " ") if closeout.get("required_action") else "") + alert_error
        checkpoint("receipt")
        hook("before_log")
        log = state_file.parent / "delivery_log.md"
        marker = f"Terminal receipt: {intent_id} / {closeout['status']} / attempt {closeout['attempts']}"
        existing = log.read_text(encoding="utf-8") if log.exists() else ""
        if marker not in existing:
            alert_file = (state.get("last_operator_alert") or {}).get("file", "unavailable")
            atomic_write_text(log, existing + f"\n## Terminal Closeout - {stamp}\n\n{marker}\nContext: {context}\nAlert: `{alert_file}`\nRequired action: {closeout.get('required_action') or 'none'}\n")
        hook("after_log")
        result = {"result": "reconcile", "status": closeout["status"], "state_status": state["status"],
                  "intent_id": intent_id, "attempts": closeout["attempts"], "receipt": deepcopy(closeout.get("receipt")),
                  "action_request": deepcopy(closeout.get("request")) if action_emitted else None,
                  "external_attempt": closeout["attempts"] if action_emitted else None,
                  "required_action": closeout.get("required_action"), "extract_phase": False,
                  "completion_claim": state["status"] == "completed", "exit_code": 0 if closeout.get("receipt") or closeout["status"] in {"disabled", "not_applicable"} else 4}
        return result
