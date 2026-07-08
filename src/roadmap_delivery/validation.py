"""Validate phase-gated roadmap delivery artifacts without mutating files."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from .adaptive import adaptive_target_from_state, validate_adaptive_model_policy
from .approval import approval_decision_for_pause_context, read_approval_policy
from .git import run_git
from .paths import (
    extract_roadmap_references,
    is_lifecycle_roadmap_sibling,
    package_repo_root,
    path_for_report,
    resolve_repo_path,
    slug_forms,
    state_candidates,
    unique,
    unique_paths,
)
from .policy import (
    ACTIVE_STATUSES,
    ALLOWED_REASONING_EFFORTS,
    COMPLETED_STATUSES,
    has_blocked_remediation_guard,
    has_hard_stop_guard,
    has_state_resolved_roadmap_guard,
    manual_activation_reconciliation,
    normalized,
    phase_number,
    reasoning_effort_exceeds,
    reasoning_effort_satisfies,
)
from .progress import ProgressSignatureError, build_run_result
from .state import JsonObjectError, load_json_object
from .toml import parse_minimal_toml


DEFAULT_AUTOMATIONS_DIR = Path.home() / ".codex" / "automations"
AUTOMATIONS_DIR = Path(os.environ.get("AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR", str(DEFAULT_AUTOMATIONS_DIR))).expanduser()
VALID_REVIEW_VERDICTS = {"delivered", "needs-fix", "blocked"}
KNOWN_NOTIFICATION_MODES = {"alert_file", "github_issue", "none", "slack", "email", "codex_thread", "webhook"}
VALID_ALERT_KINDS = {"stalled", "completed", "blocked", "retarget-failed"}
SCHEMA_FILENAMES = {
    "delivery_state": "delivery_state.schema.json",
    "phase_model_policy": "phase_model_policy.schema.json",
    "review_artifact": "review_artifact.schema.json",
    "automation_run_log": "automation_run_log.schema.json",
}
REQUIRED_ALERT_MARKERS = (
    "Roadmap:",
    "Phase:",
    "Status:",
    "Reason:",
    "Required model:",
    "Configured model:",
    "Required reasoning effort:",
    "Configured reasoning effort:",
    "Last verification:",
    "Last review:",
    "State file:",
    "Delivery log:",
    "Next human action:",
)
POLICY_STATE_FIELDS = (
    "required_model",
    "required_reasoning_effort",
    "configured_automation_model",
    "configured_automation_reasoning_effort",
    "run_count",
    "stalled_run_count",
    "max_stalled_runs",
    "last_progress_signature",
    "last_progress_at",
    "last_operator_alert",
)
DEEP_REVIEW_CANDIDATES = (
    "deep_review_prompt",
    "deep_review_prompt_path",
    "deep_review",
    "deep_review_path",
    "final_deep_review_prompt_file",
    "final_deep_review_prompt",
    "final_deep_review_review_file",
    "final_deep_review_artifact",
    "final_review_prompt",
    "final_review_artifact",
)
DEEP_REVIEW_FILENAMES = (
    "deep_review_prompt.md",
    "deep_review_prompt.txt",
    "final_deep_review_prompt.md",
    "final-deep-review-prompt.md",
    "final_review_prompt.md",
    "final-review-prompt.md",
    "final_deep_review.md",
    "final-deep-review.md",
    "review_fixes_prompt.md",
    "deep_review.md",
)
FINAL_DEEP_REVIEW_STATUSES = {"prompt-prepared", "review-complete", "waived-by-human"}
FINAL_DEEP_REVIEW_STATUS_KEYS = ("final_deep_review_status", "deep_review_status", "final_review_status")
FINAL_DEEP_REVIEW_PREPARED_KEYS = ("final_deep_review_prompt_prepared", "deep_review_prompt_prepared")
FINAL_DEEP_REVIEW_WAIVER_REASON_KEYS = (
    "final_deep_review_waiver_reason",
    "final_review_waiver_reason",
    "deep_review_waiver_reason",
)


Finding = Dict[str, str]


def add(items: List[Finding], code: str, message: str, path: Optional[Path] = None) -> None:
    item = {"code": code, "message": message}
    if path is not None:
        item["path"] = str(path)
    items.append(item)


def schema_dirs(repo_root: Path) -> List[Path]:
    candidates = [repo_root / "schemas"]
    local_root = package_repo_root()
    if local_root is not None:
        candidates.append(local_root / "schemas")
    return unique_paths(candidates)


def load_schema(
    repo_root: Path,
    schema_name: str,
    errors: List[Finding],
    warnings: List[Finding],
) -> Tuple[Optional[Dict[str, Any]], Optional[Path]]:
    filename = SCHEMA_FILENAMES[schema_name]
    for directory in schema_dirs(repo_root):
        path = directory / filename
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                schema = json.load(fh)
        except json.JSONDecodeError as exc:
            add(errors, f"invalid_{schema_name}_schema_json", f"Schema file is invalid JSON: {exc}", path)
            return None, path
        except OSError as exc:
            add(errors, f"{schema_name}_schema_unreadable", f"Cannot read schema file: {exc}", path)
            return None, path
        if not isinstance(schema, dict):
            add(errors, f"invalid_{schema_name}_schema_shape", "Schema file root is not a JSON object.", path)
            return None, path
        return schema, path
    add(warnings, f"missing_{schema_name}_schema", f"Schema file {filename!r} was not found; using built-in compatibility checks.")
    return None, None


def resolve_schema_ref(schema: Dict[str, Any], root_schema: Dict[str, Any]) -> Dict[str, Any]:
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    if not ref.startswith("#/$defs/"):
        return schema
    key = ref.rsplit("/", 1)[-1]
    defs = root_schema.get("$defs")
    if isinstance(defs, dict) and isinstance(defs.get(key), dict):
        return defs[key]
    return schema


def json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def matches_json_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def validate_json_schema(value: Any, schema: Dict[str, Any], *, root_schema: Optional[Dict[str, Any]] = None, path: str = "$") -> List[str]:
    root_schema = root_schema or schema
    schema = resolve_schema_ref(schema, root_schema)
    messages: List[str] = []

    alternatives = schema.get("oneOf") or schema.get("anyOf")
    if isinstance(alternatives, list):
        alt_errors = [
            validate_json_schema(value, alt, root_schema=root_schema, path=path)
            for alt in alternatives
            if isinstance(alt, dict)
        ]
        if not any(not errors for errors in alt_errors):
            messages.append(f"{path}: value does not match any allowed schema")
        return messages

    if "const" in schema and value != schema["const"]:
        messages.append(f"{path}: expected constant {schema['const']!r}, got {value!r}")
        return messages

    if "enum" in schema and value not in schema["enum"]:
        messages.append(f"{path}: value {value!r} is not one of {schema['enum']!r}")
        return messages

    expected_type = schema.get("type")
    if expected_type is not None:
        expected_types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(isinstance(item, str) and matches_json_type(value, item) for item in expected_types):
            messages.append(f"{path}: expected type {expected_types!r}, got {json_type_name(value)!r}")
            return messages

    if isinstance(value, dict):
        required = schema.get("required")
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    messages.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for key, prop_schema in properties.items():
                if key in value and isinstance(prop_schema, dict):
                    messages.extend(validate_json_schema(value[key], prop_schema, root_schema=root_schema, path=f"{path}.{key}"))
        additional = schema.get("additionalProperties", True)
        if isinstance(additional, dict):
            for key, item in value.items():
                if not isinstance(properties, dict) or key not in properties:
                    messages.extend(validate_json_schema(item, additional, root_schema=root_schema, path=f"{path}.{key}"))
        elif additional is False and isinstance(properties, dict):
            for key in sorted(set(value) - set(properties)):
                messages.append(f"{path}: unexpected property {key!r}")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            messages.append(f"{path}: expected at least {min_items} items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                messages.extend(validate_json_schema(item, item_schema, root_schema=root_schema, path=f"{path}[{index}]"))

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            messages.append(f"{path}: expected string length at least {min_length}")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and not re.search(pattern, value):
            messages.append(f"{path}: value {value!r} does not match pattern {pattern!r}")

    if isinstance(value, int) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, int) and value < minimum:
            messages.append(f"{path}: expected value >= {minimum}")

    return messages


def apply_schema_errors(
    schema_name: str,
    value: Dict[str, Any],
    schema: Optional[Dict[str, Any]],
    path: Path,
    errors: List[Finding],
) -> int:
    if schema is None:
        return 0
    messages = validate_json_schema(value, schema)
    for message in messages:
        add(errors, f"{schema_name}_schema_error", message, path)
    return len(messages)


def record_schema_messages(
    schema_name: str,
    messages: List[str],
    path: Path,
    errors: List[Finding],
    warnings: List[Finding],
    *,
    legacy_mode: bool = False,
    legacy_code: Optional[str] = None,
) -> int:
    for message in messages:
        if legacy_mode:
            add(warnings, legacy_code or f"legacy_{schema_name}_schema", message, path)
        else:
            add(errors, f"{schema_name}_schema_error", message, path)
    return len(messages)


def validate_versioned_state_schema(
    state: Dict[str, Any],
    state_file: Path,
    schema: Optional[Dict[str, Any]],
    errors: List[Finding],
    warnings: List[Finding],
) -> Dict[str, Any]:
    version = state.get("schema_version")
    report = {"schema_version": version, "mode": "validated" if version == 1 else "compatibility"}
    if version is None:
        add(
            warnings,
            "legacy_delivery_state_schema_version",
            "Delivery state has no schema_version; accepted in legacy compatibility mode.",
            state_file,
        )
        return report
    if version != 1:
        add(errors, "invalid_delivery_state_schema_version", "Delivery state schema_version must be 1.", state_file)
        return report
    report["error_count"] = apply_schema_errors("delivery_state", state, schema, state_file, errors)
    return report


def automation_candidates(forms: Dict[str, Optional[str]]) -> List[str]:
    candidates = []
    dash = forms.get("dash")
    directory = forms.get("dir")
    if dash:
        candidates.append(f"{dash}-delivery")
    if directory:
        candidates.append(f"{directory}-delivery")
    return unique(candidates)


def find_automation_id(forms: Dict[str, Optional[str]], warnings: List[Finding]) -> Optional[str]:
    for candidate in automation_candidates(forms):
        if (AUTOMATIONS_DIR / candidate / "automation.toml").exists():
            return candidate

    needles = [item for item in (forms.get("dash"), forms.get("dir")) if item]
    matches: List[str] = []
    if AUTOMATIONS_DIR.exists():
        for toml in AUTOMATIONS_DIR.glob("*/automation.toml"):
            try:
                text = toml.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if any(needle in text or needle in toml.parent.name for needle in needles):
                matches.append(toml.parent.name)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        add(warnings, "multiple_automation_matches", "Multiple automation configs match the slug: " + ", ".join(sorted(matches)))
    return None


def choose_state_file(repo_root: Path, forms: Dict[str, Optional[str]], errors: List[Finding]) -> Tuple[Optional[Path], Optional[Dict[str, Any]]]:
    candidates = state_candidates(repo_root, forms)
    for candidate in candidates:
        if candidate.exists():
            try:
                return candidate, load_json_object(candidate)
            except JsonObjectError as exc:
                message = str(exc)
                if message.startswith("Invalid JSON"):
                    add(errors, "invalid_state_json", f"State file is invalid JSON: {message}", candidate)
                elif message.startswith("JSON root"):
                    add(errors, "invalid_state_shape", "State file root is not a JSON object.", candidate)
                else:
                    add(errors, "state_file_unreadable", f"Cannot read state file: {exc}", candidate)
                return candidate, None

    message = "State file does not exist. Checked: " + ", ".join(str(path) for path in candidates)
    add(errors, "missing_state_file", message)
    return (candidates[0] if candidates else None), None


def read_text(path: Path, errors: List[Finding], code: str) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        add(errors, code, f"Cannot read file: {exc}", path)
        return None


def parse_roadmap_header(text: str) -> Dict[str, str]:
    header: Dict[str, str] = {}
    for line in text.splitlines()[:80]:
        match = re.match(r"^(Status|Current phase|Last completed phase|Next action):\s*(.+?)\s*$", line)
        if match:
            header[match.group(1).lower()] = match.group(2)
    return header


def is_complete_state(state: Optional[Dict[str, Any]], header: Dict[str, str]) -> bool:
    if not state:
        return False
    state_status = normalized(state.get("status"))
    current_phase = normalized(state.get("current_phase"))
    header_status = normalized(header.get("status"))
    header_phase = normalized(header.get("current phase"))
    return (
        bool(state.get("all_phases_complete"))
        or state_status in COMPLETED_STATUSES
        or current_phase in {"complete", "completed", "all-phases-complete"}
        or header_status in {"delivered", "complete", "completed"}
        or header_phase in {"complete", "completed"}
    )


def find_deep_review_prompt(state_dir: Optional[Path], state: Dict[str, Any]) -> Optional[Path]:
    finalization = state.get("finalization")
    if isinstance(finalization, dict):
        for key in DEEP_REVIEW_CANDIDATES:
            value = finalization.get(key)
            if value:
                return Path(str(value))
    for key in DEEP_REVIEW_CANDIDATES:
        value = state.get(key)
        if value:
            return Path(str(value))
    last_verification = state.get("last_verification")
    if isinstance(last_verification, dict):
        prompt = last_verification.get("deep_review_prompt")
        if prompt:
            return Path(str(prompt))
    if state_dir:
        review_dir = state_dir / "reviews"
        if review_dir.is_dir():
            for path in review_dir.glob("*deep-review-prompt.md"):
                return path
            for path in review_dir.glob("*final-deep-review*.md"):
                return path
        for name in DEEP_REVIEW_FILENAMES:
            path = state_dir / name
            if path.exists():
                return path
    return None


def first_finalization_value(state: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
    finalization = state.get("finalization")
    containers: List[Dict[str, Any]] = []
    if isinstance(finalization, dict):
        containers.append(finalization)
    containers.append(state)
    for container in containers:
        for key in keys:
            value = container.get(key)
            if value not in (None, ""):
                return value
    return None


def final_deep_review_status(state: Dict[str, Any]) -> Optional[str]:
    value = first_finalization_value(state, FINAL_DEEP_REVIEW_STATUS_KEYS)
    if value is None:
        return None
    return normalized(value)


def final_deep_review_prompt_prepared(state: Dict[str, Any]) -> Optional[bool]:
    value = first_finalization_value(state, FINAL_DEEP_REVIEW_PREPARED_KEYS)
    if isinstance(value, bool):
        return value
    return None


def final_deep_review_waiver_reason(state: Dict[str, Any]) -> Optional[str]:
    value = first_finalization_value(state, FINAL_DEEP_REVIEW_WAIVER_REASON_KEYS)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def extract_section(text: str, heading_pattern: str) -> Optional[str]:
    match = re.search(
        rf"(?ims)^##\s+{heading_pattern}\s*\n(?P<body>.*?)(?=^##\s+|\Z)",
        text,
    )
    if not match:
        return None
    return match.group("body").strip() or None


def first_metadata_value(text: str, label: str) -> Optional[str]:
    match = re.search(rf"(?im)^{re.escape(label)}:\s*(.+?)\s*$", text)
    if not match:
        return None
    value = match.group(1).strip()
    if value.startswith("`") and value.endswith("`") and len(value) >= 2:
        value = value[1:-1]
    return value


def parse_review_artifact(text: str, verdict: Optional[str]) -> Dict[str, Any]:
    return {
        "reviewed_at": first_metadata_value(text, "Reviewed at"),
        "roadmap": first_metadata_value(text, "Roadmap"),
        "phase": first_metadata_value(text, "Phase"),
        "branch": first_metadata_value(text, "Branch"),
        "reviewer_context": first_metadata_value(text, "Reviewer context"),
        "findings": extract_section(text, "Findings"),
        "missing_tests_or_checks": extract_section(text, "Missing Tests(?: Or Checks)?"),
        "verification_evidence": extract_section(text, "(?:Verification Evidence|Tests And Verification)"),
        "verdict": verdict,
    }


def validate_review_verdicts(
    review_dir: Path,
    errors: List[Finding],
    warnings: List[Finding],
    review_schema: Optional[Dict[str, Any]] = None,
    *,
    legacy_mode: bool = False,
) -> Dict[str, Any]:
    report = {"files_checked": 0, "schema_errors": 0}
    if not review_dir.exists():
        add(errors, "missing_review_dir", "Review directory does not exist.", review_dir)
        return report
    if not review_dir.is_dir():
        add(errors, "review_path_not_directory", "Review path is not a directory.", review_dir)
        return report

    review_files = sorted(review_dir.glob("*.md"))
    if not review_files:
        add(warnings, "empty_review_dir", "Review directory contains no markdown review files.", review_dir)
        return report

    for path in review_files:
        report["files_checked"] += 1
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            add(errors, "review_file_unreadable", f"Cannot read review file: {exc}", path)
            continue
        verdicts = [match.group(1).strip().lower() for match in re.finditer(r"(?im)^Verdict:\s*([A-Za-z_-]+)\s*$", text)]
        section_match = re.search(r"(?ims)^##\s+Verdict\s*\n+\s*([A-Za-z_-]+)\s*(?:\n|$)", text)
        if section_match:
            verdicts.append(section_match.group(1).strip().lower())
        if not verdicts:
            add(warnings, "missing_review_verdict", "Review file has no Verdict line.", path)
            continue
        for verdict in verdicts:
            if verdict not in VALID_REVIEW_VERDICTS:
                add(errors, "invalid_review_verdict", f"Review verdict {verdict!r} is not one of {sorted(VALID_REVIEW_VERDICTS)}.", path)
        artifact = parse_review_artifact(text, verdicts[-1])
        messages = validate_json_schema(artifact, review_schema) if review_schema is not None else []
        report["schema_errors"] += record_schema_messages(
            "review_artifact",
            messages,
            path,
            errors,
            warnings,
            legacy_mode=legacy_mode,
            legacy_code="legacy_review_artifact_schema",
        )
    return report


def load_policy(policy_path: Path, errors: List[Finding]) -> Optional[Dict[str, Any]]:
    try:
        with policy_path.open("r", encoding="utf-8") as fh:
            policy = json.load(fh)
    except json.JSONDecodeError as exc:
        add(errors, "invalid_model_policy_json", f"Policy file is invalid JSON: {exc}", policy_path)
        return None
    except OSError as exc:
        add(errors, "model_policy_unreadable", f"Cannot read policy file: {exc}", policy_path)
        return None
    if not isinstance(policy, dict):
        add(errors, "invalid_model_policy_shape", "Policy file root is not a JSON object.", policy_path)
        return None
    return policy


def validate_reasoning(value: Any, code: str, errors: List[Finding], policy_path: Path) -> None:
    if str(value or "") not in ALLOWED_REASONING_EFFORTS:
        add(errors, code, f"Reasoning effort {value!r} is not one of {sorted(ALLOWED_REASONING_EFFORTS)}.", policy_path)


def validate_model_policy(
    policy_path: Path,
    state: Dict[str, Any],
    automation_data: Dict[str, Any],
    errors: List[Finding],
    warnings: List[Finding],
    policy_schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "policy_path": str(policy_path),
        "required_model": None,
        "required_reasoning_effort": None,
        "base_required_model": None,
        "base_required_reasoning_effort": None,
        "selection_source": None,
        "selection_reason": None,
        "adaptive_policy": None,
        "configured_model": automation_data.get("model"),
        "configured_reasoning_effort": automation_data.get("reasoning_effort"),
        "configured_model_source": "automation_config" if automation_data.get("model") else None,
        "configured_reasoning_source": "automation_config" if automation_data.get("reasoning_effort") else None,
        "model_mismatch": False,
        "reasoning_mismatch": False,
        "model_unknown": False,
        "reasoning_unknown": False,
        "reasoning_satisfied": False,
        "reasoning_over_required": False,
    }
    if not policy_path.exists():
        return result

    policy = load_policy(policy_path, errors)
    if policy is None:
        return result
    apply_schema_errors("phase_model_policy", policy, policy_schema, policy_path, errors)

    if policy.get("schema_version") != 1:
        add(errors, "unsupported_model_policy_schema", "Policy schema_version must be 1.", policy_path)
    adaptive_policy = validate_adaptive_model_policy(policy)
    result["adaptive_policy"] = adaptive_policy
    for item in adaptive_policy.get("errors", []):
        add(errors, str(item.get("code") or "invalid_adaptive_policy"), str(item.get("message") or "Adaptive model policy is invalid."), policy_path)

    max_stalled = policy.get("max_stalled_runs")
    if not isinstance(max_stalled, int) or isinstance(max_stalled, bool) or max_stalled < 1:
        add(errors, "invalid_max_stalled_runs", "max_stalled_runs must be a positive integer.", policy_path)

    notification = policy.get("notification")
    if not isinstance(notification, dict):
        add(errors, "invalid_notification_policy", "notification must be an object.", policy_path)
    else:
        for key in ("mode", "fallback"):
            value = notification.get(key)
            if value is not None and value not in KNOWN_NOTIFICATION_MODES:
                add(errors, "invalid_notification_mode", f"notification.{key} {value!r} is not known.", policy_path)

    defaults = policy.get("defaults")
    if not isinstance(defaults, dict):
        add(errors, "missing_model_policy_defaults", "defaults must be an object.", policy_path)
        defaults = {}
    default_model = defaults.get("model")
    default_reasoning = defaults.get("reasoning_effort")
    if not isinstance(default_model, str) or not default_model.strip():
        add(errors, "missing_default_model", "defaults.model must be a non-empty string.", policy_path)
    if default_reasoning is None:
        add(errors, "missing_default_reasoning_effort", "defaults.reasoning_effort is required.", policy_path)
    else:
        validate_reasoning(default_reasoning, "invalid_default_reasoning_effort", errors, policy_path)

    phases = policy.get("phases")
    if not isinstance(phases, dict):
        add(errors, "invalid_phase_policy_map", "phases must be an object.", policy_path)
        phases = {}
    for phase_key, phase_policy in phases.items():
        if not isinstance(phase_policy, dict):
            add(errors, "invalid_phase_policy_entry", f"phases.{phase_key} must be an object.", policy_path)
            continue
        phase_model = phase_policy.get("model")
        phase_reasoning = phase_policy.get("reasoning_effort")
        if phase_model is not None and (not isinstance(phase_model, str) or not phase_model.strip()):
            add(errors, "invalid_phase_model", f"phases.{phase_key}.model must be a non-empty string.", policy_path)
        if phase_reasoning is not None:
            validate_reasoning(phase_reasoning, "invalid_phase_reasoning_effort", errors, policy_path)

    phase_key = phase_number(state.get("current_phase"))
    if not phase_key and normalized(state.get("current_phase")) in {"complete", "completed", "finalization"}:
        phase_key = "finalization"
    phase_policy = phases.get(phase_key, {}) if phase_key else {}
    if not isinstance(phase_policy, dict):
        phase_policy = {}
    required_model = phase_policy.get("model") or default_model
    required_reasoning = phase_policy.get("reasoning_effort") or default_reasoning
    selection_source = f"phases.{phase_key}" if phase_key and phase_key in phases else "defaults"
    selection_reason = f"Current phase target resolved from {selection_source}."
    result["base_required_model"] = required_model
    result["base_required_reasoning_effort"] = required_reasoning
    state_target = adaptive_target_from_state(state, state.get("current_phase"))
    if state_target:
        required_model = state_target.get("model") or required_model
        required_reasoning = state_target.get("reasoning_effort") or required_reasoning
        selection_source = str(state_target.get("source") or "state.last_adaptive_action")
        selection_reason = str(state_target.get("reason") or "Adaptive target recorded in delivery state.")
    result["required_model"] = required_model
    result["required_reasoning_effort"] = required_reasoning
    result["selection_source"] = selection_source
    result["selection_reason"] = selection_reason

    configured_model = automation_data.get("model") or state.get("configured_automation_model")
    configured_reasoning = automation_data.get("reasoning_effort") or state.get("configured_automation_reasoning_effort")
    result["configured_model"] = configured_model
    result["configured_reasoning_effort"] = configured_reasoning
    if configured_model and not result["configured_model_source"]:
        result["configured_model_source"] = "delivery_state"
    if configured_reasoning and not result["configured_reasoning_source"]:
        result["configured_reasoning_source"] = "delivery_state"
    if required_model and not configured_model:
        result["model_unknown"] = True
        add(
            errors,
            "automation_model_unknown",
            f"Required model {required_model!r} is defined but no configured automation or runner model was found.",
            policy_path,
        )
    if required_reasoning and not configured_reasoning:
        result["reasoning_unknown"] = True
        add(
            errors,
            "automation_reasoning_unknown",
            f"Required reasoning {required_reasoning!r} is defined but no configured automation or runner reasoning effort was found.",
            policy_path,
        )
    if required_model and configured_model and str(required_model) != str(configured_model):
        result["model_mismatch"] = True
        add(errors, "automation_model_mismatch", f"Required model {required_model!r} differs from configured model {configured_model!r}.", policy_path)
    if required_reasoning and configured_reasoning:
        result["reasoning_satisfied"] = reasoning_effort_satisfies(configured_reasoning, required_reasoning)
        result["reasoning_over_required"] = reasoning_effort_exceeds(configured_reasoning, required_reasoning)
    if required_reasoning and configured_reasoning and not result["reasoning_satisfied"]:
        result["reasoning_mismatch"] = True
        add(
            errors,
            "automation_reasoning_mismatch",
            f"Required reasoning {required_reasoning!r} exceeds configured reasoning {configured_reasoning!r}.",
            policy_path,
        )

    for field in POLICY_STATE_FIELDS:
        if field not in state:
            add(warnings, "missing_policy_state_field", f"State is missing model/stall field {field!r}.")
    for field in ("run_count", "stalled_run_count"):
        value = state.get(field)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            add(errors, "invalid_policy_state_counter", f"State field {field!r} must be a non-negative integer.")
    state_max = state.get("max_stalled_runs")
    if state_max is not None and (not isinstance(state_max, int) or isinstance(state_max, bool) or state_max < 1):
        add(errors, "invalid_policy_state_counter", "State field 'max_stalled_runs' must be a positive integer.")

    return result


def validate_progress_tracking(
    repo_root: Path,
    state_file: Path,
    state: Dict[str, Any],
    errors: List[Finding],
    warnings: List[Finding],
) -> Optional[Dict[str, Any]]:
    try:
        progress = build_run_result(repo_root, state_file, state)
    except ProgressSignatureError as exc:
        add(errors, "progress_signature_failed", str(exc), state_file)
        return None

    for item in progress.get("run_log_errors", []):
        path = Path(str(item.get("path"))) if item.get("path") else state_file.parent / "automation_run_log.jsonl"
        line = item.get("line")
        suffix = f" line {line}" if line is not None else ""
        add(errors, "invalid_run_log_jsonl", f"{path}{suffix}: {item.get('message')}", path)

    state_max = state.get("max_stalled_runs")
    policy_max = progress.get("max_stalled_runs")
    if state_max is not None and policy_max and state_max != policy_max:
        add(
            warnings,
            "state_policy_stall_threshold_mismatch",
            f"State max_stalled_runs {state_max!r} differs from policy/default threshold {policy_max!r}.",
            state_file,
        )

    if progress.get("threshold_reached") and normalized(state.get("status")) != "blocked":
        add(
            warnings,
            "stalled_threshold_pending",
            "Next recorded no-progress run would reach the stalled threshold and should block before further delivery.",
            state_file,
        )

    return progress


def validate_run_log_schema(
    state_file: Path,
    run_log_schema: Optional[Dict[str, Any]],
    errors: List[Finding],
) -> Dict[str, Any]:
    report = {"path": str(state_file.parent / "automation_run_log.jsonl"), "entries_checked": 0, "schema_errors": 0}
    if run_log_schema is None:
        return report
    run_log_path = state_file.parent / "automation_run_log.jsonl"
    if not run_log_path.exists():
        return report
    try:
        lines = run_log_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        add(errors, "automation_run_log_unreadable", f"Cannot read automation run log: {exc}", run_log_path)
        return report

    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        report["entries_checked"] += 1
        messages = validate_json_schema(value, run_log_schema)
        for message in messages:
            report["schema_errors"] += 1
            add(errors, "automation_run_log_schema_error", f"line {number}: {message}", run_log_path)
    return report


def validate_operator_alert(
    repo_root: Path,
    state_dir: Path,
    state: Dict[str, Any],
    errors: List[Finding],
    warnings: List[Finding],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "alert_dir": str(state_dir / "alerts"),
        "last_operator_alert": state.get("last_operator_alert"),
    }
    alert_dir = state_dir / "alerts"
    if alert_dir.exists() and not alert_dir.is_dir():
        add(errors, "operator_alert_path_not_directory", "Alert path exists but is not a directory.", alert_dir)
        return result

    last_alert = state.get("last_operator_alert")
    if last_alert is None:
        if normalized(state.get("status")) == "blocked" and state.get("blocked_reason"):
            add(warnings, "blocked_state_missing_operator_alert", "Blocked state has a blocked_reason but no last_operator_alert.")
        return result
    if not isinstance(last_alert, dict):
        add(errors, "invalid_operator_alert_state", "last_operator_alert must be an object when present.")
        return result

    kind = last_alert.get("kind")
    if kind not in VALID_ALERT_KINDS:
        add(errors, "invalid_operator_alert_kind", f"Alert kind {kind!r} is not one of {sorted(VALID_ALERT_KINDS)}.")

    file_value = last_alert.get("file")
    if not isinstance(file_value, str) or not file_value.strip():
        add(errors, "missing_operator_alert_file", "last_operator_alert.file must be a non-empty path.")
        return result
    alert_path = resolve_repo_path(repo_root, file_value)
    result["alert_file"] = str(alert_path) if alert_path else None
    if not alert_path or not alert_path.exists():
        add(errors, "missing_operator_alert_file", "Recorded operator alert file does not exist.", alert_path)
        return result
    if not alert_path.is_file():
        add(errors, "operator_alert_not_file", "Recorded operator alert path is not a file.", alert_path)
        return result

    text = read_text(alert_path, errors, "operator_alert_unreadable")
    if text is not None:
        for marker in REQUIRED_ALERT_MARKERS:
            if marker not in text:
                add(errors, "operator_alert_missing_context", f"Alert file is missing required marker {marker!r}.", alert_path)
        if kind and f"Alert kind: `{kind}`" not in text and f"Alert kind: {kind}" not in text:
            add(warnings, "operator_alert_kind_not_visible", "Alert file does not visibly include the recorded alert kind.", alert_path)

    notification_status = last_alert.get("notification_status")
    notification_failure = last_alert.get("notification_failure")
    if notification_status == "failed" and not notification_failure:
        add(warnings, "operator_alert_failure_missing_reason", "Notification status is failed but no notification_failure was recorded.")
    if notification_failure and notification_status != "failed":
        add(warnings, "operator_alert_failure_status_mismatch", "notification_failure is present but notification_status is not failed.")

    return result


def validate_completion_flow(
    repo_root: Path,
    state: Dict[str, Any],
    complete: bool,
    operator_alert: Optional[Dict[str, Any]],
    automation_status: Optional[str],
    approval_policy: Optional[Dict[str, Any]],
    errors: List[Finding],
    warnings: List[Finding],
) -> Dict[str, Any]:
    completion_pause_decision = approval_decision_for_pause_context(approval_policy or {}, "completion")
    last_pause = state.get("last_automation_pause")
    result: Dict[str, Any] = {
        "complete": complete,
        "completion_alert_present": False,
        "completion_pause_required": complete and str(automation_status).upper() == "ACTIVE",
        "automation_should_be_paused": complete and str(automation_status).upper() != "PAUSED",
        "completion_pause_decision": completion_pause_decision,
        "last_automation_pause": last_pause,
    }
    if not complete:
        return result

    state_status = normalized(state.get("status"))
    automation_is_active = str(automation_status).upper() == "ACTIVE"
    if (
        automation_is_active
        and state_status != "completed-pending-pause"
        and completion_pause_decision.get("decision") == "allowed"
    ):
        add(
            errors,
            "completed_state_pause_readback_missing",
            "Completion pause is allowed by policy, but completed state does not read back a PAUSED automation.",
        )
    if isinstance(last_pause, dict):
        pause_result = last_pause.get("result") if isinstance(last_pause.get("result"), dict) else {}
        readback_status = last_pause.get("readback_status") or pause_result.get("readback_status")
        result_status = last_pause.get("status")
        if result_status in {"paused", "already_paused"} and str(readback_status or "").upper() != "PAUSED":
            add(
                errors,
                "automation_pause_readback_mismatch",
                "State records a successful automation pause but readback_status is not PAUSED.",
            )

    last_alert = state.get("last_operator_alert")
    if not isinstance(last_alert, dict):
        add(errors, "completed_state_missing_completed_alert", "Completed state does not record a completed operator alert.")
        return result

    kind = last_alert.get("kind")
    result["completion_alert_kind"] = kind
    file_value = last_alert.get("file")
    if isinstance(file_value, str) and file_value.strip():
        alert_path = resolve_repo_path(repo_root, file_value)
        result["completion_alert_file"] = str(alert_path) if alert_path else None
    else:
        alert_path = None

    if kind != "completed":
        add(errors, "completed_state_missing_completed_alert", f"Completed state records alert kind {kind!r}, not 'completed'.")
        return result
    if not alert_path or not alert_path.exists() or not alert_path.is_file():
        add(errors, "completed_state_missing_completed_alert", "Completed state records a completed alert, but the alert file is missing.", alert_path)
        return result

    alert_report = operator_alert or {}
    if not alert_report.get("last_operator_alert"):
        add(errors, "completed_state_missing_completed_alert", "Completed state alert was not validated.")
    else:
        result["completion_alert_present"] = True
    if last_alert.get("notification_status") == "failed" and not last_alert.get("notification_failure"):
        add(warnings, "completion_notification_failure_missing_reason", "Completed alert notification failed without a recorded failure reason.")
    return result


def validate_approval_policy_state(
    state: Dict[str, Any],
    approval_policy: Optional[Dict[str, Any]],
    state_file: Path,
    errors: List[Finding],
    warnings: List[Finding],
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "state_approval_mode": state.get("approval_mode"),
        "effective_approval_mode": approval_policy.get("approval_mode") if approval_policy else None,
        "fallback_reason": approval_policy.get("fallback_reason") if approval_policy else None,
        "last_readback_status": None,
    }
    if approval_policy is None:
        return report

    policy_path_value = approval_policy.get("path")
    policy_path = Path(policy_path_value) if isinstance(policy_path_value, str) and policy_path_value else state_file
    for flag in ("pause_automation_on_completion", "pause_automation_on_stall"):
        reason_key = f"{flag}_reason"
        if approval_policy.get(flag) is False and not str(approval_policy.get(reason_key) or "").strip():
            add(
                warnings,
                "safety_pause_disabled_without_reason",
                (
                    f"{flag} is false without an opt-out reason. This can indicate an old setup artifact "
                    "that silently preserved the deprecated human-gated terminal pause behavior."
                ),
                policy_path,
            )

    state_mode = state.get("approval_mode")
    effective_mode = approval_policy.get("approval_mode")
    fallback_reason = approval_policy.get("fallback_reason")
    if isinstance(state_mode, str) and state_mode:
        if fallback_reason == "missing_policy" and state_mode != "conservative":
            add(
                errors,
                "approval_policy_state_mismatch",
                f"State approval_mode {state_mode!r} requires an approval_policy.json, but validation fell back to conservative because the policy is missing.",
                state_file,
            )
        elif effective_mode and state_mode != effective_mode:
            add(
                errors,
                "approval_policy_state_mismatch",
                f"State approval_mode {state_mode!r} differs from effective approval mode {effective_mode!r}.",
                state_file,
            )

    readback = state.get("last_approval_policy_readback")
    if readback is None:
        return report
    if not isinstance(readback, dict):
        add(errors, "invalid_approval_policy_readback", "last_approval_policy_readback must be an object when present.", state_file)
        return report

    status = normalized(readback.get("status"))
    report["last_readback_status"] = status
    if status == "valid" and fallback_reason:
        add(
            errors,
            "approval_policy_readback_stale",
            f"State records a valid approval-policy readback, but current validation is using {fallback_reason!r} conservative fallback.",
            state_file,
        )
    readback_mode = readback.get("approval_mode")
    if isinstance(readback_mode, str) and effective_mode and readback_mode != effective_mode:
        add(
            errors,
            "approval_policy_readback_stale",
            f"Recorded approval-policy readback mode {readback_mode!r} differs from effective mode {effective_mode!r}.",
            state_file,
        )

    readback_operations = readback.get("approved_operations")
    if status == "valid" and isinstance(readback_operations, list):
        recorded = {item for item in readback_operations if isinstance(item, str)}
        effective = set(approval_policy.get("approved_operations") or [])
        if recorded != effective:
            add(
                errors,
                "approval_policy_readback_stale",
                "Recorded approved operations differ from the effective approval policy.",
                state_file,
            )
    elif status == "valid" and readback_operations is not None:
        add(errors, "invalid_approval_policy_readback", "last_approval_policy_readback.approved_operations must be an array when present.", state_file)

    return report


def validate_final_deep_review_gate(
    repo_root: Path,
    state_dir: Optional[Path],
    state: Dict[str, Any],
    complete: bool,
    errors: List[Finding],
    warnings: List[Finding],
) -> Dict[str, Any]:
    status = final_deep_review_status(state)
    prompt_prepared = final_deep_review_prompt_prepared(state)
    waiver_reason = final_deep_review_waiver_reason(state)
    prompt = find_deep_review_prompt(state_dir, state)
    result: Dict[str, Any] = {
        "required": complete,
        "status": status,
        "prompt_prepared": prompt_prepared,
        "prompt": str(prompt) if prompt else None,
        "prompt_file": None,
        "prompt_exists": False,
        "waived": status == "waived-by-human",
        "waiver_reason": waiver_reason,
    }
    if not complete:
        return result

    if status is not None and status not in FINAL_DEEP_REVIEW_STATUSES:
        add(
            errors,
            "invalid_final_deep_review_status",
            f"Final deep-review status {status!r} is not one of {sorted(FINAL_DEEP_REVIEW_STATUSES)}.",
        )

    if status == "waived-by-human":
        if not waiver_reason:
            add(
                errors,
                "final_deep_review_waiver_missing_reason",
                "Final deep review was waived, but no human waiver reason is recorded.",
            )
        return result

    if prompt is None:
        add(
            errors,
            "completed_state_missing_final_deep_review_prompt",
            "Completed state must record or colocate a final deep-review prompt/review artifact, "
            "or record final_deep_review_status 'waived-by-human' with a waiver reason before "
            "all_phases_complete/completed_pending_pause.",
        )
        return result

    deep_review_path = resolve_repo_path(repo_root, str(prompt))
    result["prompt_file"] = str(deep_review_path) if deep_review_path else str(prompt)
    if not deep_review_path or not deep_review_path.exists():
        add(errors, "final_deep_review_prompt_missing_file", "Final deep-review prompt path does not exist.", deep_review_path)
    elif not deep_review_path.is_file():
        add(errors, "final_deep_review_prompt_not_file", "Final deep-review prompt path is not a file.", deep_review_path)
    else:
        result["prompt_exists"] = True

    if prompt_prepared is False:
        add(
            errors,
            "final_deep_review_prompt_not_prepared",
            "Completed state explicitly records final_deep_review_prompt_prepared as false.",
        )
    elif prompt_prepared is None:
        add(
            warnings,
            "final_deep_review_metadata_missing",
            "Completed state has a final deep-review prompt, but does not record final_deep_review_prompt_prepared.",
        )
    if status is None:
        add(
            warnings,
            "final_deep_review_status_missing",
            "Completed state has a final deep-review prompt, but does not record final_deep_review_status.",
        )
    return result


def validate_branch(repo_root: Path, forms: Dict[str, Optional[str]], state: Dict[str, Any], complete: bool, warnings: List[Finding]) -> Dict[str, Optional[str]]:
    branch_info: Dict[str, Optional[str]] = {"current_branch": None, "expected_branch": None}
    proc = run_git(repo_root, ["branch", "--show-current"])
    if proc.returncode == 0:
        branch_info["current_branch"] = proc.stdout.strip()
    else:
        add(warnings, "git_branch_failed", proc.stderr.strip() or "git branch --show-current failed")

    current_phase = state.get("current_phase")
    number = phase_number(current_phase)
    dash = forms.get("dash") or normalized(state.get("roadmap_slug"))
    if number and dash:
        expected = f"codex/{dash}-phase-{number}"
        branch_info["expected_branch"] = expected
        state_branch = state.get("branch")
        if state_branch and str(state_branch) != expected:
            add(warnings, "state_branch_name_mismatch", f"State branch {state_branch!r} does not match expected {expected!r}.")
        current = branch_info["current_branch"]
        if current and current != expected and not complete:
            add(warnings, "current_branch_name_mismatch", f"Current branch {current!r} does not match expected {expected!r}.")

    return branch_info


def validate_lifecycle_filename(roadmap_path: Optional[Path], header: Dict[str, str], complete: bool, errors: List[Finding], warnings: List[Finding]) -> None:
    if not roadmap_path:
        return
    name = roadmap_path.name
    header_status = normalized(header.get("status"))
    header_phase_number = phase_number(header.get("current phase"))
    started_phase = header_phase_number is not None and int(header_phase_number) >= 1
    header_active = header_status in ACTIVE_STATUSES
    has_not_started_prefix = name.startswith("not_started_")
    has_delivered_prefix = name.startswith("delivered_")
    has_in_progress_prefix = name.startswith("in_progress_")

    if has_not_started_prefix and (header_active or started_phase):
        add(
            errors,
            "roadmap_lifecycle_filename_mismatch",
            "Active roadmap or Phase 1+ roadmap still uses a not_started_ lifecycle filename.",
            roadmap_path,
        )
    elif complete and has_in_progress_prefix:
        add(errors, "roadmap_lifecycle_filename_mismatch", "Completed roadmap still uses an in_progress filename.", roadmap_path)
    elif complete and not has_delivered_prefix:
        add(warnings, "roadmap_lifecycle_filename_unconfirmed", "Completed roadmap does not use the delivered_ lifecycle filename convention.", roadmap_path)
    elif header_active and has_delivered_prefix:
        add(errors, "roadmap_lifecycle_filename_mismatch", "Active roadmap status uses a delivered_ filename.", roadmap_path)


def validate(repo_root: Path, roadmap_slug: Optional[str], automation_id: Optional[str]) -> Dict[str, Any]:
    errors: List[Finding] = []
    warnings: List[Finding] = []
    info: List[Finding] = []

    repo_root = repo_root.expanduser().resolve()
    if not repo_root.is_dir():
        add(errors, "repo_root_missing", "--repo-root is not a directory.", repo_root)
        return {"errors": errors, "warnings": warnings, "info": info}

    schemas: Dict[str, Optional[Dict[str, Any]]] = {}
    schema_paths: Dict[str, Optional[str]] = {}
    for schema_name in SCHEMA_FILENAMES:
        schema, schema_path = load_schema(repo_root, schema_name, errors, warnings)
        schemas[schema_name] = schema
        schema_paths[schema_name] = str(schema_path) if schema_path else None

    forms = slug_forms(roadmap_slug)
    if not automation_id:
        automation_id = find_automation_id(forms, warnings)

    automation_toml: Optional[Path] = None
    automation_status: Optional[str] = None
    automation_prompt = ""
    hard_stop_guard = False
    blocked_remediation_guard = False
    automation_data: Dict[str, Any] = {}
    if automation_id:
        automation_toml = AUTOMATIONS_DIR / automation_id / "automation.toml"
        if automation_toml.exists():
            try:
                automation_data = parse_minimal_toml(automation_toml)
            except OSError as exc:
                add(errors, "automation_config_unreadable", f"Cannot read automation config: {exc}", automation_toml)
                automation_data = {}
            automation_status = str(automation_data.get("status") or "")
            automation_prompt = str(automation_data.get("prompt") or "")
            hard_stop_guard = has_hard_stop_guard(automation_prompt)
            blocked_remediation_guard = has_blocked_remediation_guard(automation_prompt)
        else:
            add(warnings, "missing_automation_config", "Automation config does not exist.", automation_toml)
    else:
        add(warnings, "automation_config_not_found", "No automation config was found for the supplied slug.")

    state_file, state = choose_state_file(repo_root, forms, errors)
    state_dir = state_file.parent if state_file else None
    delivery_log = state_dir / "delivery_log.md" if state_dir else None
    review_dir = state_dir / "reviews" if state_dir else None

    if not state:
        return {
            "automation_id": automation_id,
            "automation_status": automation_status,
            "automation_toml": path_for_report(automation_toml),
            "repo_root": str(repo_root),
            "state_file": path_for_report(state_file),
            "schema_validation": {"schema_paths": schema_paths},
            "errors": errors,
            "warnings": warnings,
            "info": info,
        }

    state_schema_report = validate_versioned_state_schema(
        state,
        state_file,
        schemas.get("delivery_state"),
        errors,
        warnings,
    ) if state_file else None

    state_slug = state.get("roadmap_slug")
    if state_slug and not roadmap_slug:
        forms = slug_forms(str(state_slug))
    elif state_slug and roadmap_slug and normalized(state_slug) != normalized(roadmap_slug):
        add(warnings, "roadmap_slug_mismatch", f"Requested slug {roadmap_slug!r} differs from state roadmap_slug {state_slug!r}.")

    if delivery_log is None or not delivery_log.exists():
        add(errors, "missing_delivery_log", "Delivery log does not exist.", delivery_log)
    elif not delivery_log.is_file():
        add(errors, "delivery_log_not_file", "Delivery log path is not a file.", delivery_log)

    review_schema_report = None
    if review_dir is not None:
        review_schema_report = validate_review_verdicts(
            review_dir,
            errors,
            warnings,
            schemas.get("review_artifact"),
            legacy_mode=bool(state_schema_report and state_schema_report.get("mode") == "compatibility"),
        )

    state_roadmap_value = state.get("roadmap")
    roadmap_path = resolve_repo_path(repo_root, str(state_roadmap_value)) if state_roadmap_value else None
    roadmap_text = None
    roadmap_header: Dict[str, str] = {}
    if not roadmap_path:
        add(errors, "missing_state_roadmap", "State does not define a roadmap path.")
    elif not roadmap_path.exists():
        add(errors, "missing_roadmap_file", "Roadmap path from state does not exist.", roadmap_path)
    else:
        roadmap_text = read_text(roadmap_path, errors, "roadmap_unreadable")
        if roadmap_text is not None:
            roadmap_header = parse_roadmap_header(roadmap_text)

    complete = is_complete_state(state, roadmap_header)
    validate_lifecycle_filename(roadmap_path, roadmap_header, complete, errors, warnings)

    if roadmap_header:
        state_phase = normalized(state.get("current_phase"))
        header_phase = normalized(roadmap_header.get("current phase"))
        if state_phase and header_phase and state_phase not in {"complete", "completed"} and header_phase not in {"complete", "completed"} and state_phase != header_phase:
            add(errors, "current_phase_mismatch", f"State current_phase {state.get('current_phase')!r} differs from roadmap Current phase {roadmap_header.get('current phase')!r}.")

    automation_refs = extract_roadmap_references(automation_prompt, repo_root) if automation_prompt else []
    state_resolved_roadmap_prompt = has_state_resolved_roadmap_guard(automation_prompt)
    if automation_prompt and roadmap_path:
        if not automation_refs:
            if not state_resolved_roadmap_prompt:
                add(warnings, "automation_prompt_missing_roadmap_path", "Automation prompt does not include a recognizable roadmap markdown path or a state-resolved roadmap guard.", automation_toml)
        elif roadmap_path not in automation_refs:
            if not state_resolved_roadmap_prompt:
                add(warnings, "automation_prompt_current_roadmap_missing", f"Automation prompt does not reference current roadmap path {roadmap_path}.", automation_toml)
        for ref in automation_refs:
            lifecycle_only_drift = state_resolved_roadmap_prompt and is_lifecycle_roadmap_sibling(ref, roadmap_path)
            if ref != roadmap_path and not ref.exists() and not lifecycle_only_drift:
                add(warnings, "stale_automation_roadmap_path", f"Automation prompt references missing roadmap path {ref}; state points to {roadmap_path}.", automation_toml)
            elif ref != roadmap_path and not lifecycle_only_drift:
                add(warnings, "automation_roadmap_path_mismatch", f"Automation prompt references {ref}; state points to {roadmap_path}.", automation_toml)

    if automation_prompt and not hard_stop_guard:
        add(warnings, "automation_prompt_missing_hard_stop_guard", "Automation prompt does not include an all_phases_complete/completed_pending_pause hard-stop guard.", automation_toml)
    if automation_prompt and not blocked_remediation_guard:
        add(warnings, "automation_prompt_missing_blocked_remediation_guard", "Automation prompt does not include Blocked Remediation Mode.", automation_toml)
    if normalized(state.get("status")) == "blocked" and str(automation_status).upper() == "ACTIVE" and not blocked_remediation_guard:
        add(errors, "blocked_state_active_without_remediation_guard", "State is blocked and automation is ACTIVE without Blocked Remediation Mode.", automation_toml)

    approval_policy = read_approval_policy(repo_root, state_file, state) if state_file else None
    if approval_policy is not None:
        errors.extend(approval_policy.get("errors", []))
    approval_policy_state = validate_approval_policy_state(
        state,
        approval_policy,
        state_file,
        errors,
        warnings,
    ) if state_file else None

    policy_path = state_dir / "phase_model_policy.json" if state_dir else None
    model_policy: Dict[str, Any] = {}
    if policy_path is not None:
        model_policy = validate_model_policy(policy_path, state, automation_data, errors, warnings, schemas.get("phase_model_policy"))
    progress_tracking = validate_progress_tracking(repo_root, state_file, state, errors, warnings) if state_file else None
    run_log_schema_report = validate_run_log_schema(state_file, schemas.get("automation_run_log"), errors) if state_file else None
    operator_alert = validate_operator_alert(repo_root, state_dir, state, errors, warnings) if state_dir else None
    completion_flow = validate_completion_flow(repo_root, state, complete, operator_alert, automation_status, approval_policy, errors, warnings)
    final_deep_review = validate_final_deep_review_gate(repo_root, state_dir, state, complete, errors, warnings)
    deep_review_prompt = Path(str(final_deep_review["prompt"])) if final_deep_review.get("prompt") else None
    activation_reconciliation = manual_activation_reconciliation(
        state,
        automation_status,
        model_policy,
        blocked_remediation_guard=blocked_remediation_guard,
        hard_stop_guard=hard_stop_guard,
        complete=complete,
    )
    if activation_reconciliation.get("available"):
        add(
            info,
            "manual_activation_reconciliation_available",
            "Saved automation is ACTIVE while blocked reason records PAUSED/ACTIVE drift; this can be repaired by recording accepted activation.",
            automation_toml,
        )

    if complete and str(automation_status).upper() == "ACTIVE":
        if hard_stop_guard:
            add(warnings, "completed_state_active_with_hard_stop", "State is complete and automation is ACTIVE, but prompt contains an explicit hard-stop guard.", automation_toml)
        else:
            add(errors, "completed_state_active_automation", "State is complete but automation is ACTIVE and lacks an explicit hard-stop guard.", automation_toml)

    branch_info = validate_branch(repo_root, forms, state, complete, warnings)

    status_proc = run_git(repo_root, ["status", "--short"])
    worktree_dirty = False
    if status_proc.returncode == 0:
        worktree_dirty = bool(status_proc.stdout.strip())
        if worktree_dirty:
            add(warnings, "worktree_dirty", "Repository has uncommitted changes.")
    else:
        add(warnings, "git_status_failed", status_proc.stderr.strip() or "git status --short failed")

    add(info, "state_file", "Validated delivery state file.", state_file)
    if roadmap_path:
        add(info, "roadmap_path", "Validated roadmap path from state.", roadmap_path)
    if delivery_log:
        add(info, "delivery_log", "Checked delivery log path.", delivery_log)
    if review_dir:
        add(info, "review_dir", "Checked review directory.", review_dir)

    return {
        "automation_id": automation_id,
        "automation_status": automation_status,
        "automation_toml": path_for_report(automation_toml),
        "automation_roadmap_references": [str(path) for path in automation_refs],
        "hard_stop_guard": hard_stop_guard,
        "blocked_remediation_guard": blocked_remediation_guard,
        "state_resolved_roadmap_prompt": state_resolved_roadmap_prompt,
        "activation_reconciliation": activation_reconciliation,
        "approval_policy": approval_policy,
        "approval_policy_state": approval_policy_state,
        "model_policy": model_policy or None,
        "schema_validation": {
            "schema_paths": schema_paths,
            "delivery_state": state_schema_report,
            "review_artifacts": review_schema_report,
            "automation_run_log": run_log_schema_report,
        },
        "progress_tracking": progress_tracking,
        "operator_alert": operator_alert,
        "completion_flow": completion_flow,
        "final_deep_review": final_deep_review,
        "repo_root": str(repo_root),
        "roadmap_slug": roadmap_slug or state.get("roadmap_slug"),
        "state_file": path_for_report(state_file),
        "delivery_log": path_for_report(delivery_log),
        "review_dir": path_for_report(review_dir),
        "roadmap_path": path_for_report(roadmap_path),
        "roadmap_status": roadmap_header.get("status"),
        "roadmap_current_phase": roadmap_header.get("current phase"),
        "state_status": state.get("status"),
        "state_current_phase": state.get("current_phase"),
        "all_phases_complete": complete,
        "deep_review_prompt": str(deep_review_prompt) if deep_review_prompt else None,
        "current_branch": branch_info.get("current_branch"),
        "expected_branch": branch_info.get("expected_branch"),
        "worktree_dirty": worktree_dirty,
        "errors": errors,
        "warnings": warnings,
        "info": info,
    }


def print_text(report: Dict[str, Any]) -> None:
    for key in (
        "automation_id",
        "automation_status",
        "roadmap_path",
        "state_file",
        "state_status",
        "state_current_phase",
        "all_phases_complete",
        "activation_reconciliation",
        "current_branch",
        "expected_branch",
        "worktree_dirty",
    ):
        if key in report:
            print(f"{key}: {report.get(key)}")
    for section in ("errors", "warnings", "info"):
        items = report.get(section) or []
        print(f"{section}: {len(items)}")
        for item in items:
            suffix = f" [{item['path']}]" if item.get("path") else ""
            print(f"- {item['code']}: {item['message']}{suffix}")


def parse_allowed_warning_codes(values: Optional[List[str]]) -> set[str]:
    codes: set[str] = set()
    for value in values or []:
        for code in value.split(","):
            cleaned = code.strip()
            if cleaned:
                codes.add(cleaned)
    return codes


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate phase-gated roadmap delivery artifacts without mutating files.")
    parser.add_argument("--repo-root", required=True, help="Repository root to validate.")
    parser.add_argument("--roadmap-slug", help="Roadmap slug, accepting hyphen or underscore form.")
    parser.add_argument("--automation-id", help="Codex automation id under ~/.codex/automations.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when warnings are present.")
    parser.add_argument(
        "--allow-warning",
        action="append",
        default=[],
        metavar="CODE",
        help="Warning code to allow under --strict. May be repeated or comma-separated.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    if not args.roadmap_slug and not args.automation_id:
        parser.error("at least one of --roadmap-slug or --automation-id is required")

    report = validate(Path(args.repo_root), args.roadmap_slug, args.automation_id)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)

    if report.get("errors"):
        return 1
    if args.strict:
        allowed_warnings = parse_allowed_warning_codes(args.allow_warning)
        blocking_warnings = [item for item in report.get("warnings", []) if item.get("code") not in allowed_warnings]
        if blocking_warnings:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
