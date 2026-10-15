"""Compute and optionally record durable roadmap delivery progress."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import os
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

from .approval import approval_decision_for_pause_context, read_approval_policy
from .control import account_run_outcome, account_verified_repair, decide_control, scope_complete
from .git import run_git
from .paths import slug_forms, state_candidates as state_file_candidates
from .state import JsonObjectError, load_json_object, review_verdict, write_json_object


DEFAULT_MAX_STALLED_RUNS = 2
RUN_LOG_FILENAME = "automation_run_log.jsonl"
SIGNATURE_VERSION = 1  # Historical diagnostics only; never an accounting input.
EVIDENCE_VERSION = 1
JOURNAL_VERSION = 2


class ProgressSignatureError(RuntimeError):
    """Raised when progress cannot be computed or recorded safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def state_candidates(repo_root: Path, roadmap_slug: str) -> List[Path]:
    forms = slug_forms(roadmap_slug)
    return state_file_candidates(repo_root, forms)


def find_state_file(repo_root: Path, roadmap_slug: str) -> Path:
    candidates = state_candidates(repo_root, roadmap_slug)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    checked = ", ".join(str(path) for path in candidates) or "<none>"
    raise ProgressSignatureError(f"State file does not exist. Checked: {checked}")


def load_progress_json_object(path: Path) -> Dict[str, Any]:
    try:
        return load_json_object(path)
    except JsonObjectError as exc:
        raise ProgressSignatureError(str(exc)) from exc


def write_progress_json_object(path: Path, value: Dict[str, Any]) -> None:
    try:
        write_json_object(path, value)
    except JsonObjectError as exc:
        raise ProgressSignatureError(str(exc)) from exc


def relative_or_absolute(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def non_negative_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int) and value >= 0:
        return value
    return default


def positive_int(value: Any, default: int = DEFAULT_MAX_STALLED_RUNS) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int) and value > 0:
        return value
    return default


def git_head(repo_root: Path) -> Optional[str]:
    proc = run_git(repo_root, ["rev-parse", "HEAD"])
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def file_fingerprint(repo_root: Path, path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {
            "path": relative_or_absolute(repo_root, path),
            "exists": False,
            "size": None,
            "sha256": None,
        }
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        stat = path.stat()
    except OSError as exc:
        raise ProgressSignatureError(f"Cannot fingerprint {path}: {exc}") from exc
    return {
        "path": relative_or_absolute(repo_root, path),
        "exists": True,
        "size": stat.st_size,
        "sha256": digest.hexdigest(),
    }


def progress_signature_input(repo_root: Path, state_file: Path, state: Dict[str, Any]) -> Dict[str, Any]:
    delivery_log = state_file.parent / "delivery_log.md"
    return {
        "signature_version": SIGNATURE_VERSION,
        "current_phase": state.get("current_phase"),
        "status": state.get("status"),
        "last_delivered_phase": state.get("last_delivered_phase"),
        "review_iterations": state.get("review_iterations"),
        "last_verification": state.get("last_verification"),
        "last_review": state.get("last_review"),
        "git_head": git_head(repo_root),
        "delivery_log": file_fingerprint(repo_root, delivery_log),
        "blocked_reason": state.get("blocked_reason"),
    }


def compute_progress_signature(repo_root: Path, state_file: Path, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = state if state is not None else load_progress_json_object(state_file)
    signature_input = progress_signature_input(repo_root, state_file, state)
    digest = hashlib.sha256(canonical_json(signature_input).encode("utf-8")).hexdigest()
    return {
        "progress_signature": f"sha256:{digest}",
        "signature_input": signature_input,
    }


def policy_max_stalled_runs(policy_path: Path) -> Tuple[int, str]:
    if not policy_path.exists():
        return DEFAULT_MAX_STALLED_RUNS, "default"
    try:
        policy = load_json_object(policy_path)
    except JsonObjectError:
        return DEFAULT_MAX_STALLED_RUNS, "default"
    value = policy.get("max_stalled_runs")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value, "phase_model_policy"
    return DEFAULT_MAX_STALLED_RUNS, "default"


def parse_run_log(run_log_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    entries: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    if not run_log_path.exists():
        return entries, errors
    try:
        lines = run_log_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return entries, [{"line": None, "message": f"Cannot read run log: {exc}", "path": str(run_log_path)}]
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append({"line": number, "message": f"Invalid JSONL entry: {exc}", "path": str(run_log_path)})
            continue
        if not isinstance(value, dict):
            errors.append({"line": number, "message": "Run log entry is not a JSON object.", "path": str(run_log_path)})
            continue
        entries.append(value)
    return entries, errors


def _counter(state: Dict[str, Any], name: str) -> int:
    value = state.get(name, 0)
    if type(value) is not int or value < 0:
        raise ProgressSignatureError(f"{name} must be a non-negative integer; refusing history loss.")
    return value


def _event_keys(item: Dict[str, Any]) -> List[str]:
    """Do not use supplied semantic IDs, verifier paths or wording as identity."""
    identity = item["previous"].get("blocked_reason") if item["kind"] == "blocker_resolved" else item.get("criterion_id")
    scope = [item["phase"], item["kind"], identity]
    if item["kind"] == "blocker_resolved" and item["previous"].get("blocker_occurrence_id"):
        scope.append(item["previous"]["blocker_occurrence_id"])
    if item["kind"] == "accepted_phase_work":
        return [canonical_json(scope + [item["increment_id"]]),
                canonical_json(scope + [item["current"]["artifact_sha256"]])]
    return [canonical_json(scope)]


def _migration(state: Dict[str, Any], entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    count = _counter(state, "run_count")
    stalled = _counter(state, "stalled_run_count")
    if stalled > count:
        raise ProgressSignatureError("Consecutive count exceeds lifetime runs; reconcile history explicitly.")
    keys = []
    legacy_ids = []
    for entry in entries:
        if entry.get("schema_version") == JOURNAL_VERSION:
            continue
        for field in ("run_count", "stalled_run_count"):
            if field in entry:
                _counter(entry, field)
        if not isinstance(entry.get("semantic_progress_evidence", []), list):
            raise ProgressSignatureError("Malformed legacy evidence history.")
        if entry.get("run_id"):
            if not isinstance(entry["run_id"], str):
                raise ProgressSignatureError("Malformed legacy run identity.")
            if entry["run_id"] in legacy_ids:
                raise ProgressSignatureError("Duplicate legacy run ID; reconcile history explicitly.")
            legacy_ids.append(entry["run_id"])
        # Bootstrap accepted events become consumed, never newly earned progress.
        for item in entry.get("semantic_progress_evidence", []):
            if isinstance(item, dict) and item.get("criterion_id"):
                phase = entry.get("phase") or entry.get("current_phase")
                keys.append(canonical_json([phase, "criterion_satisfied", item["criterion_id"]]))
                keys.append(canonical_json([phase, "accepted_phase_work", item["criterion_id"], item.get("artifact_sha256")]))
    known_runs = max([len(legacy_ids)] + [non_negative_int(e.get("run_count")) for e in entries])
    if known_runs > count:
        raise ProgressSignatureError("Run log has more known runs than state; refusing to erase history.")
    if entries and non_negative_int(entries[-1].get("stalled_run_count")) > stalled:
        raise ProgressSignatureError("Run log has more known consecutive failures; reconcile history explicitly.")
    return {"schema_version": EVIDENCE_VERSION, "revision": 0, "attempt_epoch": 0,
            "consumed_events": sorted(set(keys)),
            "blocker_context": {"reason": state["blocked_reason"]} if state.get("blocked_reason") else None,
            "migration": {"baseline_run_count": count, "baseline_stalled_run_count": stalled,
                          "legacy_run_ids": legacy_ids,
                          "legacy_signature": state.get("last_progress_signature"),
                          "uncertain_history": bool(state.get("last_progress_signature") or count != len(legacy_ids)
                                                    or any(e.get("progress_signature") for e in entries)),
                          "note": "Preserved known counters; old hashes are diagnostics, migration is not progress."}}


def _replay(state: Dict[str, Any], entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    state = deepcopy(state)
    state.setdefault("run_count", _counter(state, "run_count"))
    state.setdefault("stalled_run_count", _counter(state, "stalled_run_count"))
    accounting = state.get("progress_accounting")
    if accounting is None:
        accounting = _migration(state, [e for e in entries if e.get("schema_version") != JOURNAL_VERSION])
        state["progress_accounting"] = accounting
    if (not isinstance(accounting, dict) or type(accounting.get("schema_version")) is not int or accounting["schema_version"] != EVIDENCE_VERSION
            or type(accounting.get("revision")) is not int or accounting["revision"] < 0
            or not isinstance(accounting.get("consumed_events"), list)
            or any(not isinstance(k, str) for k in accounting["consumed_events"])):
        raise ProgressSignatureError("Invalid semantic accounting state.")
    revision = accounting["revision"]
    last_revision = 0
    started = set()
    completed = set()
    latest = None
    for entry in entries:
        if entry.get("schema_version") != JOURNAL_VERSION:
            continue
        if (entry.get("revision_before") != last_revision or entry.get("revision_after") != last_revision + 1
                or type(entry.get("revision_before")) is not int or type(entry.get("revision_after")) is not int
                or entry.get("event_type") not in {"run_started", "run_completed", "blocker_repaired"}
                or not isinstance(entry.get("state_changes"), dict) or not isinstance(entry.get("run_id"), str)
                or not entry["run_id"].strip()):
            raise ProgressSignatureError("Conflicting or malformed accounting journal revision.")
        snapshot = entry["state_changes"]
        ledger = snapshot.get("progress_accounting")
        if (not isinstance(ledger, dict) or ledger.get("schema_version") != EVIDENCE_VERSION
                or ledger.get("revision") != entry["revision_after"]
                or not isinstance(ledger.get("consumed_events"), list)
                or any(not isinstance(k, str) for k in ledger["consumed_events"])
                or not isinstance(ledger.get("migration"), dict)
                or not isinstance(ledger["migration"].get("legacy_run_ids"), list)
                or type(ledger.get("attempt_epoch")) is not int or ledger["attempt_epoch"] < 0
                or type(snapshot.get("run_count")) is not int or type(snapshot.get("stalled_run_count")) is not int
                or snapshot["stalled_run_count"] < 0 or snapshot["run_count"] < snapshot["stalled_run_count"]):
            raise ProgressSignatureError("Malformed accounting journal state snapshot.")
        if entry["event_type"] in {"run_completed", "blocker_repaired"} and not isinstance(entry.get("result"), dict):
            raise ProgressSignatureError("Malformed accounting journal outcome.")
        run_id = entry["run_id"]
        if entry["event_type"] == "run_started":
            if run_id in started:
                raise ProgressSignatureError("Duplicate journal start.")
            started.add(run_id)
        elif entry["event_type"] == "run_completed":
            if run_id not in started or run_id in completed:
                raise ProgressSignatureError("Conflicting or orphaned journal outcome.")
            completed.add(run_id)
        last_revision = entry["revision_after"]
        latest = entry
        if last_revision > revision:
            if scope_complete(state):
                raise ProgressSignatureError("Completed scope requires terminal closeout; pending accounting journal needs explicit reconciliation.")
            state.update(deepcopy(entry["state_changes"]))
    if revision > last_revision:
        raise ProgressSignatureError("State revision is ahead of journal; refusing to lose runs.")
    if latest:
        for key in ("run_count", "stalled_run_count", "active_run", "progress_accounting"):
            if state.get(key) != latest["state_changes"].get(key):
                raise ProgressSignatureError(f"State/journal conflict in {key}; explicit reconciliation required.")
    accounting = state["progress_accounting"]
    active = state.get("active_run")
    if (not isinstance(accounting.get("migration"), dict)
            or not isinstance(accounting["migration"].get("legacy_run_ids"), list)
            or type(accounting.get("attempt_epoch")) is not int or accounting["attempt_epoch"] < 0
            or len(set(accounting["consumed_events"])) != len(accounting["consumed_events"])
            or (accounting.get("blocker_context") is not None and not isinstance(accounting["blocker_context"], dict))
            or (active is not None and (not isinstance(active, dict) or not active.get("run_id")
                                       or not isinstance(active.get("phase"), str)
                                       or not isinstance(active.get("initial_evidence"), list)))):
        raise ProgressSignatureError("Malformed accounting envelope or active attempt.")
    _counter(state, "run_count")
    _counter(state, "stalled_run_count")
    return state


def _artifact(repo_root: Path, reference: Dict[str, Any]) -> Path:
    if (not isinstance(reference, dict) or not isinstance(reference.get("path"), str)
            or not reference["path"] or Path(reference["path"]).is_absolute()):
        raise ProgressSignatureError("Evidence artifact must have a repository-relative path.")
    path = (repo_root / reference["path"]).resolve()
    try:
        path.relative_to(repo_root.resolve())
    except ValueError:
        raise ProgressSignatureError("Evidence artifact escapes repository.")
    fingerprint = file_fingerprint(repo_root, path)
    if not fingerprint["exists"] or not fingerprint["size"] or fingerprint["sha256"] != reference.get("sha256"):
        raise ProgressSignatureError(f"Missing or changed evidence artifact: {reference['path']}")
    return path


def validate_semantic_evidence(repo_root: Path, active: Dict[str, Any], items: Any) -> List[Dict[str, Any]]:
    """Validate artifact-bound check/reviewer attestations, not author claims.

    Verifier JSON is a trust boundary: a check or reviewer must produce it. We
    verify its scope, transitions and artifact integrity; we cannot authenticate
    the person who wrote a local file. Only accepted work also requires review.
    """
    if not isinstance(items, list):
        raise ProgressSignatureError("Semantic evidence must be a list.")
    validated = []
    for item in items:
        if not isinstance(item, dict):
            raise ProgressSignatureError("Semantic evidence item must be an object.")
        payload = {k: v for k, v in item.items() if k != "verifier"}
        kind = item.get("kind")
        if type(item.get("schema_version")) is not int or item["schema_version"] != EVIDENCE_VERSION or item.get("phase") != active["phase"]:
            raise ProgressSignatureError("Evidence version/phase does not match the active attempt.")
        if kind not in {"accepted_phase_work", "criterion_satisfied", "blocker_resolved"}:
            raise ProgressSignatureError("Unknown progress evidence kind.")
        identity = "blocker_id" if kind == "blocker_resolved" else "criterion_id"
        if not isinstance(item.get(identity), str) or not item[identity].strip():
            raise ProgressSignatureError("Evidence needs a stable criterion or blocker ID.")
        previous = item.get("previous")
        current = item.get("current")
        if not isinstance(previous, dict) or not isinstance(current, dict):
            raise ProgressSignatureError("Evidence requires initial and final semantic states.")
        expected = {"accepted_phase_work": "accepted", "criterion_satisfied": "passed", "blocker_resolved": "resolved"}[kind]
        if current.get("status") != expected or previous.get("status") not in {"unmet", "blocked"}:
            raise ProgressSignatureError("No newly satisfied semantic transition is evidenced.")
        artifact = _artifact(repo_root, {"path": current.get("artifact"), "sha256": current.get("artifact_sha256")})
        if previous.get("artifact_sha256") == current.get("artifact_sha256"):
            raise ProgressSignatureError("Unchanged artifact cannot prove new accepted work or repair.")
        if kind == "accepted_phase_work":
            if not isinstance(item.get("increment_id"), str) or not item["increment_id"].strip():
                raise ProgressSignatureError("Accepted work needs a stable implementation increment ID.")
            if current["artifact"] not in active.get("owned_files", []):
                raise ProgressSignatureError("Accepted artifact is not owned by this phase.")
        if kind == "blocker_resolved":
            if not active.get("blocked_reason") or previous.get("blocked_reason") != active["blocked_reason"]:
                raise ProgressSignatureError("Repair must verify the original actionable blocker.")
            if previous.get("blocker_occurrence_id") != active.get("blocker_occurrence_id"):
                raise ProgressSignatureError("Repair must verify the current blocker occurrence.")
        # Routine automation records cannot prove accepted implementation.
        if artifact.name in {"delivery_state.json", "delivery_log.md", RUN_LOG_FILENAME} or "reviews" in artifact.parts:
            raise ProgressSignatureError("Bookkeeping is not semantic progress.")
        verifier_path = _artifact(repo_root, item.get("verifier", {}))
        verifier = load_progress_json_object(verifier_path)
        if (verifier.get("schema_version") != EVIDENCE_VERSION or verifier.get("result") != "verified"
                or not isinstance(verifier.get("evidence"), list) or payload not in verifier["evidence"]):
            raise ProgressSignatureError("Verifier does not attest this exact semantic transition.")
        check = verifier.get("check", {})
        if not isinstance(check, dict) or check.get("result") != "passed":
            raise ProgressSignatureError("Progress requires a passed validating check.")
        _artifact(repo_root, check)
        if kind == "accepted_phase_work":
            review = _artifact(repo_root, verifier.get("review", {}))
            review_text = review.read_text(encoding="utf-8")
            if review_verdict(review_text) != "delivered" or item["criterion_id"] not in review_text:
                raise ProgressSignatureError("Accepted work lacks criterion-specific delivered review.")
        validated.append({**deepcopy(item), "event_keys": _event_keys(item)})
    return validated


@contextmanager
def _recording_lock(state_file: Path):
    try:
        import fcntl
    except ImportError as exc:
        raise ProgressSignatureError("This host lacks the required local recording lock capability.") from exc
    with (state_file.parent / ".progress.lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProgressSignatureError("Another writer is recording this attempt; retry the same run ID.") from exc
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def append_run_log(run_log_path: Path, entry: Dict[str, Any]) -> None:
    try:
        with run_log_path.open("a", encoding="utf-8") as fh:
            fh.write(canonical_json(entry) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except OSError as exc:
        raise ProgressSignatureError(f"Cannot append run log {run_log_path}: {exc}") from exc


def _load_recording(state_file: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    entries, errors = parse_run_log(state_file.parent / RUN_LOG_FILENAME)
    if errors:
        first = errors[0]
        raise ProgressSignatureError(f"Run log is corrupt at line {first.get('line')}: {first.get('message')}")
    return _replay(load_progress_json_object(state_file), entries), entries


def _journal(state_file: Path, state: Dict[str, Any], changes: Dict[str, Any], entry: Dict[str, Any]) -> None:
    revision = state["progress_accounting"]["revision"]
    changes["progress_accounting"]["revision"] = revision + 1
    full = {**deepcopy(state), **changes}
    journal = {"schema_version": JOURNAL_VERSION, "revision_before": revision,
               "revision_after": revision + 1, **entry,
               "state_changes": {key: deepcopy(full.get(key)) for key in
                                 ("progress_accounting", "run_count", "stalled_run_count", "max_stalled_runs",
                                  "active_run", "last_completed_run_id", "stall_metadata", "blocked_reason",
                                  "last_blocker_repair", "status", "last_progress_at", "updated_at")}}
    # Write-ahead outcome: recovery applies this exact proposal if state replace fails.
    append_run_log(state_file.parent / RUN_LOG_FILENAME, journal)
    write_progress_json_object(state_file, full)


def start_run(repo_root: Path, state_file: Path, run_id: str, *, timestamp: Optional[str] = None,
              owned_files: Optional[List[str]] = None, expected_revision: Optional[int] = None) -> Dict[str, Any]:
    if not isinstance(run_id, str) or not run_id.strip():
        raise ProgressSignatureError("A stable unique run ID is required.")
    with _recording_lock(state_file):
        state, entries = _load_recording(state_file)
        if scope_complete(state):
            raise ProgressSignatureError("Completed scope requires terminal closeout, not a new attempt.")
        revision = state["progress_accounting"]["revision"]
        if expected_revision is not None and expected_revision != revision:
            raise ProgressSignatureError("Recording revision changed; conflicting writer must stop.")
        active = state.get("active_run")
        if active:
            if not isinstance(active, dict) or active.get("run_id") != run_id:
                raise ProgressSignatureError("Recover/close the unfinished run before allocating another ID.")
            write_progress_json_object(state_file, state)
            return {"run_id": run_id, "started": True, "duplicate": True, "active_run": active}
        if any(e.get("run_id") == run_id for e in entries) or run_id in state["progress_accounting"]["migration"]["legacy_run_ids"]:
            raise ProgressSignatureError("Run ID already completed; use outcome recovery instead of reopening it.")
        if state.get("all_phases_complete") is True or str(state.get("status")).startswith("completed"):
            raise ProgressSignatureError("Completed scope requires terminal closeout, not a new attempt.")
        threshold, source = policy_max_stalled_runs(state_file.parent / "phase_model_policy.json")
        if state["stalled_run_count"] >= threshold:
            raise ProgressSignatureError("Stall threshold reached; terminal reconciliation must precede a new attempt.")
        stamp = timestamp or utc_now()
        context = state["progress_accounting"].get("blocker_context")
        if not context and state.get("blocked_reason"):
            context = {"reason": state["blocked_reason"]}
            state["progress_accounting"]["blocker_context"] = context
        if context and not context.get("occurrence_id"):
            context["occurrence_id"] = hashlib.sha256(canonical_json(
                [state.get("current_phase"), revision, run_id]).encode("utf-8")).hexdigest()
        active = {"run_id": run_id, "phase": state.get("current_phase"), "started_at": stamp,
                  "attempt_epoch": state["progress_accounting"]["attempt_epoch"],
                  "runner_identity": deepcopy(state.get("automation")), "owned_files": owned_files or [],
                  "initial_evidence": list(state["progress_accounting"]["consumed_events"]),
                  "initial_counters": {"run_count": state["run_count"], "stalled_run_count": state["stalled_run_count"]},
                  "blocked_reason": context["reason"] if context else None,
                  "blocker_occurrence_id": context.get("occurrence_id") if context else None}
        _journal(state_file, state, {"active_run": active, "max_stalled_runs": threshold,
                                     "progress_accounting": deepcopy(state["progress_accounting"]), "updated_at": stamp},
                 {"event_type": "run_started", "run_id": run_id, "timestamp": stamp, "phase": active["phase"],
                  "max_stalled_runs_source": source, "initial_evidence": active["initial_evidence"]})
        return {"run_id": run_id, "started": True, "duplicate": False, "active_run": active}


def build_run_result(repo_root: Path, state_file: Path, state: Optional[Dict[str, Any]] = None, *,
                     timestamp: Optional[str] = None, run_id: Optional[str] = None,
                     semantic_evidence: Optional[List[Dict[str, Any]]] = None,
                     outcome: str = "completed") -> Dict[str, Any]:
    entries, errors = parse_run_log(state_file.parent / RUN_LOG_FILENAME)
    state = _replay(state if state is not None else load_progress_json_object(state_file), entries)
    if run_id and scope_complete(state):
        raise ProgressSignatureError("Completed scope requires terminal closeout, not run accounting.")
    for entry in entries:
        if run_id and entry.get("event_type") == "run_completed" and entry.get("run_id") == run_id:
            return {**deepcopy(entry["result"]), "duplicate": True, "run_log_errors": errors}
    threshold, source = policy_max_stalled_runs(state_file.parent / "phase_model_policy.json")
    state["max_stalled_runs"] = threshold
    active = state.get("active_run")
    accepted = []
    changes = {}
    detected = False
    if run_id:
        if scope_complete(state):
            raise ProgressSignatureError("Completed scope requires terminal closeout, not run accounting.")
        if not isinstance(active, dict) or active.get("run_id") != run_id:
            raise ProgressSignatureError("Start this run once before recording its outcome.")
        accepted = validate_semantic_evidence(repo_root, active, [] if semantic_evidence is None else semantic_evidence)
        run_evidence = {"run_id": run_id, "validated": True, "items": accepted, "outcome": outcome}
        try:
            accounting = account_run_outcome(state, run_evidence)
        except (ValueError, KeyError, TypeError) as exc:
            raise ProgressSignatureError(str(exc)) from exc
        changes = accounting["proposed_state_changes"]
        # A cause may first appear during the run that reaches the stall limit.
        # Journal its identity with that outcome, before repair-only reconciliation.
        reason = changes.get("blocked_reason", state.get("blocked_reason"))
        context = changes["progress_accounting"].get("blocker_context")
        if reason and not (context or {}).get("occurrence_id"):
            changes["progress_accounting"]["blocker_context"] = {
                "reason": reason,
                "occurrence_id": hashlib.sha256(canonical_json(
                    [active.get("phase"), state["progress_accounting"]["revision"], run_id, reason]
                ).encode("utf-8")).hexdigest(),
            }
        detected = accounting["progress_detected"]
        accepted = accounting["accepted_evidence"]
    signature = compute_progress_signature(repo_root, state_file, state)
    count = changes.get("run_count", state["run_count"])
    stalled = changes.get("stalled_run_count", state["stalled_run_count"])
    reached = stalled >= threshold
    result = {"schema_version": EVIDENCE_VERSION, "timestamp": timestamp or utc_now(), "run_id": run_id,
              "outcome": outcome, "outcome_pending": not bool(run_id), "duplicate": False,
              "state_file": str(state_file), "run_log_path": str(state_file.parent / RUN_LOG_FILENAME),
              "run_log_entries": len(entries), "run_log_errors": errors,
              "previous_run_count": state["run_count"], "run_count": count,
              "previous_stalled_run_count": state["stalled_run_count"], "stalled_run_count": stalled,
              "max_stalled_runs": threshold, "max_stalled_runs_source": source,
              "progress_detected": detected, "accepted_evidence": accepted,
              "initial_evidence": active.get("initial_evidence", []) if isinstance(active, dict) else [],
              "final_evidence": changes.get("progress_accounting", state["progress_accounting"])["consumed_events"],
              "progress_accounting": changes.get("progress_accounting", state["progress_accounting"]),
              "threshold_reached": reached, "terminal_closeout_required": reached,
              "phase_6_alert_required": reached, "status_before": state.get("status"),
              "status_after": changes.get("status", state.get("status")),
              "blocked_reason_after": changes.get("blocked_reason", state.get("blocked_reason")),
              "proposed_state_changes": changes, "stall_pause_decision": None,
              "last_run_quality": state.get("last_run_quality"), "last_adaptive_action": state.get("last_adaptive_action"),
              "progress_signature": signature["progress_signature"], "signature_input": signature["signature_input"],
              "previous_progress_signature": state.get("last_progress_signature"),
              "signature_authority": "diagnostic_only"}
    if reached:
        policy = read_approval_policy(repo_root, state_file, state)
        result["stall_pause_decision"] = approval_decision_for_pause_context(policy, "stall")
        result["terminal_plan"] = decide_control({**state, **changes}, policy)
    return result


def record_run_result(repo_root: Path, state_file: Path, *, timestamp: Optional[str] = None,
                      automation_id: Optional[str] = None, run_id: Optional[str] = None,
                      semantic_evidence: Optional[List[Dict[str, Any]]] = None,
                      outcome: str = "completed", expected_revision: Optional[int] = None) -> Dict[str, Any]:
    """Record once; terminal effects are separately resumed by the host adapter.

    automation_id remains a compatibility argument, never authority to edit a
    live configuration. The Phase 3 closeout adapter consumes terminal_plan.
    """
    with _recording_lock(state_file):
        state, entries = _load_recording(state_file)
        run_id = run_id or (state.get("active_run") or {}).get("run_id")
        if not run_id:
            raise ProgressSignatureError("--run-id or an unfinished start record is required.")
        if expected_revision is not None and expected_revision != state["progress_accounting"]["revision"]:
            raise ProgressSignatureError("Recording revision changed; conflicting writer must stop.")
        result = build_run_result(repo_root, state_file, state, timestamp=timestamp, run_id=run_id,
                                  semantic_evidence=semantic_evidence, outcome=outcome)
        if result["duplicate"]:
            write_progress_json_object(state_file, state)
            return {**result, "recorded": True}
        changes = result["proposed_state_changes"]
        changes["updated_at"] = result["timestamp"]
        if result["progress_detected"]:
            changes["last_progress_at"] = result["timestamp"]
        active = state["active_run"]
        _journal(state_file, state, changes,
                 {"event_type": "run_completed", "run_id": run_id, "timestamp": result["timestamp"],
                  "completed_at": result["timestamp"], "phase": active["phase"], "status": result["status_after"],
                  "outcome": outcome, "initial_evidence": result["initial_evidence"],
                  "semantic_progress_evidence": result["accepted_evidence"],
                  "run_quality": state.get("last_run_quality"), "adaptive_action": state.get("last_adaptive_action"),
                  "result": deepcopy(result)})
        return {**result, "recorded": True}


def print_text(result: Dict[str, Any]) -> None:
    for key in ("state_file", "run_id", "outcome_pending", "duplicate", "signature_authority", "progress_detected",
                "run_count", "stalled_run_count", "max_stalled_runs", "threshold_reached", "run_log_path"):
        print(f"{key}: {result.get(key)}")


def record_verified_repair(repo_root: Path, state_file: Path, semantic_evidence: List[Dict[str, Any]], *,
                           timestamp: Optional[str] = None, expected_revision: Optional[int] = None) -> Dict[str, Any]:
    """Reconcile proven external repair at threshold; never allocate an attempt."""
    with _recording_lock(state_file):
        state, entries = _load_recording(state_file)
        if state.get("all_phases_complete") is True or str(state.get("status")).startswith("completed"):
            raise ProgressSignatureError("Completed scope requires completion closeout.")
        if expected_revision is not None and expected_revision != state["progress_accounting"]["revision"]:
            raise ProgressSignatureError("Recording revision changed; conflicting writer must stop.")
        if not isinstance(semantic_evidence, list) or not semantic_evidence:
            raise ProgressSignatureError("Repair-only reconciliation requires evidence.")
        try:
            keys = sorted(set(key for item in semantic_evidence for key in _event_keys(item)))
        except (KeyError, TypeError, AttributeError) as exc:
            raise ProgressSignatureError("Malformed repair evidence.") from exc
        context = state["progress_accounting"].get("blocker_context")
        for entry in entries:
            if (not context and not state.get("blocked_reason")
                    and entry.get("event_type") == "blocker_repaired" and entry.get("repair_keys") == keys
                    and [{k: v for k, v in item.items() if k != "event_keys"}
                         for item in entry.get("semantic_progress_evidence", [])] == semantic_evidence):
                write_progress_json_object(state_file, state)
                return {**deepcopy(entry["result"]), "duplicate": True, "recorded": True,
                        "progress_detected": False, "proposed_state_changes": {},
                        "run_count": state["run_count"], "stalled_run_count": state["stalled_run_count"],
                        "threshold_reached": state["stalled_run_count"] >= state["max_stalled_runs"]}
        active = {"phase": state.get("current_phase"),
                  "blocked_reason": context["reason"] if context else state.get("blocked_reason"),
                  "blocker_occurrence_id": context.get("occurrence_id") if context else None}
        validated = validate_semantic_evidence(repo_root, active, semantic_evidence)
        run_id = "repair:" + hashlib.sha256(canonical_json(keys).encode("utf-8")).hexdigest()
        evidence = {"run_id": run_id, "validated": True, "items": validated, "outcome": "completed"}
        try:
            result = account_verified_repair(state, evidence)
        except (ValueError, KeyError, TypeError) as exc:
            raise ProgressSignatureError(str(exc)) from exc
        if not result["progress_detected"]:
            return {**result, "duplicate": True, "recorded": False}
        stamp = timestamp or utc_now()
        changes = result["proposed_state_changes"]
        changes.update(updated_at=stamp, last_progress_at=stamp)
        result.update(timestamp=stamp, run_count=state["run_count"], stalled_run_count=0, duplicate=False)
        _journal(state_file, state, changes,
                 {"event_type": "blocker_repaired", "run_id": run_id, "timestamp": stamp,
                  "phase": active["phase"], "repair_keys": keys, "result": deepcopy(result),
                  "semantic_progress_evidence": validated})
        return {**result, "recorded": True}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect semantic progress or start/record one unique attempt.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--roadmap-slug")
    parser.add_argument("--state-file")
    parser.add_argument("--automation-id", help="Compatibility identity argument; no runner mutation.")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--start-run", action="store_true")
    action.add_argument("--record-run", action="store_true")
    action.add_argument("--recover-run", action="store_true", help="Close an unfinished attempt once as interrupted.")
    action.add_argument("--resolve-blocker", action="store_true", help="Consume verified external repair without a delivery attempt.")
    parser.add_argument("--run-id", help="Stable ID allocated once before phase work; reuse on retry.")
    parser.add_argument("--owned-file", action="append", default=[])
    parser.add_argument("--evidence-file", help="JSON list of verifier-backed semantic evidence.")
    parser.add_argument("--expected-revision", type=int)
    parser.add_argument("--timestamp")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()
    if args.state_file:
        state_file = Path(args.state_file).expanduser()
        if not state_file.is_absolute():
            state_file = repo_root / state_file
    elif args.roadmap_slug:
        state_file = find_state_file(repo_root, args.roadmap_slug)
    else:
        parser.error("one of --roadmap-slug or --state-file is required")
    try:
        evidence = None
        if args.evidence_file:
            path = Path(args.evidence_file)
            if not path.is_absolute():
                path = repo_root / path
            evidence = json.loads(path.read_text(encoding="utf-8"))
        if args.resolve_blocker:
            result = record_verified_repair(repo_root, state_file, evidence, timestamp=args.timestamp,
                                            expected_revision=args.expected_revision)
        elif args.start_run:
            result = start_run(repo_root, state_file, args.run_id, timestamp=args.timestamp,
                               owned_files=args.owned_file, expected_revision=args.expected_revision)
        elif args.record_run or args.recover_run:
            result = record_run_result(repo_root, state_file, timestamp=args.timestamp, run_id=args.run_id,
                                       semantic_evidence=evidence, expected_revision=args.expected_revision,
                                       outcome="interrupted" if args.recover_run else "completed")
        else:
            result = build_run_result(repo_root, state_file, timestamp=args.timestamp)
            result["recorded"] = False
    except (ProgressSignatureError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print_text(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
