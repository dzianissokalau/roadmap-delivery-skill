"""Inspect phase-gated roadmap delivery state without mutating files."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .adaptive import adaptive_target_from_state, validate_adaptive_model_policy
from .approval import approval_decision_for_pause_context, read_approval_policy
from .git import run_git
from .paths import (
    automation_dir_candidates,
    extract_roadmap_references,
    is_lifecycle_roadmap_sibling,
    resolve_repo_path,
    slug_forms,
    state_candidates,
    unique,
)
from .policy import (
    ACTIVE_STATUSES,
    ALLOWED_REASONING_EFFORTS,
    COMPLETED_STATUSES,
    has_hard_stop_guard,
    has_blocked_remediation_guard,
    has_state_resolved_roadmap_guard,
    manual_activation_reconciliation,
    normalized,
    phase_number,
    reasoning_effort_exceeds,
    reasoning_effort_satisfies,
)
from .progress import ProgressSignatureError, build_run_result
from .state import JsonObjectError, load_json_object, write_json_object
from .toml import parse_minimal_toml


DEFAULT_AUTOMATIONS_DIR = Path.home() / ".codex" / "automations"
AUTOMATIONS_DIR = Path(os.environ.get("AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR", str(DEFAULT_AUTOMATIONS_DIR))).expanduser()
GITHUB_ACTION_REPORT_SCHEMA_VERSION = 1
EVIDENCE_BENCHMARK_SCHEMA_VERSION = 1
HOST_COVERAGE_REPORT_SCHEMA_VERSION = 1
HOST_CAPABILITY_FILES = ("codex.yaml", "claude.yaml", "generic.yaml")
EVIDENCE_BENCHMARK_SCENARIOS = (
    {
        "id": "clean_delivery",
        "name": "Clean delivery evidence",
        "expected_valid": True,
        "expected_issue_codes": [],
        "description": "The committed demo fixture should validate and inspect cleanly.",
    },
    {
        "id": "missing_review_artifact",
        "name": "Missing review artifact",
        "expected_valid": False,
        "expected_issue_codes": ["review_artifact_missing"],
        "description": "State points at a delivered review file that is absent from the fixture.",
    },
    {
        "id": "stale_lifecycle_filename",
        "name": "Stale lifecycle filename",
        "expected_valid": False,
        "expected_issue_codes": ["roadmap_lifecycle_filename_mismatch"],
        "description": "An active Phase 1 roadmap is recorded under a not_started lifecycle filename.",
    },
    {
        "id": "mismatched_automation_status",
        "name": "Mismatched automation status",
        "expected_valid": False,
        "expected_issue_codes": ["automation_status_mismatch"],
        "description": "State records ACTIVE while the saved temporary automation config reads PAUSED.",
    },
    {
        "id": "insufficient_verification_evidence",
        "name": "Insufficient verification evidence",
        "expected_valid": False,
        "expected_issue_codes": ["verification_evidence_missing"],
        "description": "The delivered state keeps a passed verification record without concrete checks.",
    },
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
DEEP_REVIEW_STATE_KEYS = (
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
FINAL_DEEP_REVIEW_STATUSES = {"prompt-prepared", "review-complete", "waived-by-human"}
FINAL_DEEP_REVIEW_STATUS_KEYS = ("final_deep_review_status", "deep_review_status", "final_review_status")
FINAL_DEEP_REVIEW_PREPARED_KEYS = ("final_deep_review_prompt_prepared", "deep_review_prompt_prepared")
FINAL_DEEP_REVIEW_WAIVER_REASON_KEYS = (
    "final_deep_review_waiver_reason",
    "final_review_waiver_reason",
    "deep_review_waiver_reason",
)
LIFECYCLE_ACTIVE_STATE_STATUSES = {"active", "in progress", "in-progress"}


class EvidenceBenchmarkError(RuntimeError):
    """Raised when the local evidence benchmark cannot build a fixture."""


def split_action_values(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    for value in values:
        for chunk in str(value).replace(",", "\n").splitlines():
            item = chunk.strip()
            if item:
                result.append(item)
    return result


def clean_yaml_scalar(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value[0] in {'"', "'"} and value[-1:] == value[0]:
        return value[1:-1]
    return value


def extract_yaml_scalar(text: str, key: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}:\s*(?P<value>.+?)\s*$", re.MULTILINE)
    match = pattern.search(text)
    return clean_yaml_scalar(match.group("value")) if match else ""


def extract_capability_block(text: str, capability: str) -> str:
    lines = text.splitlines()
    block: List[str] = []
    in_block = False
    for line in lines:
        if line.startswith("  ") and not line.startswith("    "):
            if in_block:
                break
            if line.strip() == f"{capability}:":
                in_block = True
                block.append(line)
            continue
        if in_block:
            block.append(line)
    return "\n".join(block)


def extract_block_scalar(block: str, key: str) -> str:
    pattern = re.compile(rf"^\s+{re.escape(key)}:\s*(?P<value>.+?)\s*$", re.MULTILINE)
    match = pattern.search(block)
    return clean_yaml_scalar(match.group("value")) if match else ""


def skipped_checks_from_smoke_report(report: Dict[str, Any]) -> List[Dict[str, str]]:
    result: List[Dict[str, str]] = []
    for item in report.get("checks", []):
        if not isinstance(item, dict) or item.get("status") != "skipped":
            continue
        result.append(
            {
                "name": str(item.get("name") or "unknown"),
                "reason": str(item.get("reason") or "skipped"),
            }
        )
    return result


def build_host_coverage_report(
    repo_root: Path,
    *,
    smoke_reports: Iterable[Dict[str, Any]] = (),
) -> Dict[str, Any]:
    repo_root = repo_root.expanduser().resolve()
    smoke_by_host = {
        str(report.get("host")): report
        for report in smoke_reports
        if isinstance(report, dict) and report.get("host")
    }
    hosts: List[Dict[str, Any]] = []

    for filename in HOST_CAPABILITY_FILES:
        capability_path = repo_root / "host-capabilities" / filename
        try:
            text = capability_path.read_text(encoding="utf-8")
        except OSError:
            continue
        host = extract_yaml_scalar(text, "host") or capability_path.stem
        live_block = extract_capability_block(text, "live_smoke_harness")
        smoke_report = smoke_by_host.get(host, {})
        skipped_checks = skipped_checks_from_smoke_report(smoke_report)
        hosts.append(
            {
                "host": host,
                "capability_file": relative_path(repo_root, capability_path),
                "support_status": extract_yaml_scalar(text, "support_status"),
                "live_smoke_status": extract_block_scalar(live_block, "status"),
                "offline_parity": extract_block_scalar(live_block, "offline_parity"),
                "live_status_source": extract_block_scalar(live_block, "live_status_source"),
                "skipped_result_visibility": extract_block_scalar(live_block, "skipped_result_visibility"),
                "nightly_workflow": extract_block_scalar(live_block, "nightly_workflow"),
                "fallback": extract_block_scalar(live_block, "fallback"),
                "smoke_report_status": str(smoke_report.get("status") or "not-run"),
                "offline_status": str(smoke_report.get("offline_status") or "not-run"),
                "live_status": str(smoke_report.get("live_status") or "not-run"),
                "skipped_checks": skipped_checks,
            }
        )

    skipped_live_checks = [
        {
            "host": item["host"],
            "check": skipped["name"],
            "reason": skipped["reason"],
        }
        for item in hosts
        for skipped in item["skipped_checks"]
    ]
    counts = {
        "hosts": len(hosts),
        "optional_live_smoke_hosts": sum(
            1 for item in hosts if str(item.get("live_smoke_status", "")).startswith("optional")
        ),
        "future_work_hosts": sum(
            1 for item in hosts if str(item.get("live_smoke_status")) in {"host_specific_adapter_required", "future_work"}
        ),
        "smoke_reports": len(smoke_by_host),
        "skipped_live_checks": len(skipped_live_checks),
        "failed_live_checks": sum(1 for item in hosts if item.get("live_status") == "failed"),
    }
    if counts["failed_live_checks"]:
        status = "failed"
    elif counts["skipped_live_checks"]:
        status = "warning"
    else:
        status = "ok"
    return {
        "schema_version": HOST_COVERAGE_REPORT_SCHEMA_VERSION,
        "status": status,
        "repo_root": str(repo_root),
        "counts": counts,
        "hosts": hosts,
        "skipped_live_checks": skipped_live_checks,
    }


def action_default_path(repo_root: Path, suffix: str) -> Path:
    runner_temp = os.environ.get("RUNNER_TEMP")
    root = Path(runner_temp).expanduser() if runner_temp else repo_root
    if not root.is_absolute():
        root = repo_root / root
    return root / f"roadmap-delivery-validate.{suffix}"


def resolve_action_report_file(repo_root: Path, value: str, report_format: str) -> Path:
    suffix = "json" if report_format == "json" else "txt"
    path = Path(value).expanduser() if value else action_default_path(repo_root, suffix)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def resolve_github_output_file(repo_root: Path, value: str) -> Path:
    raw = value or os.environ.get("GITHUB_OUTPUT") or ""
    path = Path(raw).expanduser() if raw else action_default_path(repo_root, "outputs")
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def run_action_json(command: Sequence[str], cwd: Path) -> Dict[str, Any]:
    proc = subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        payload: Any = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"stdout": proc.stdout.strip()}
    return {
        "command": list(command),
        "returncode": proc.returncode,
        "stdout": payload,
        "stderr": proc.stderr.strip(),
    }


def command_status(result: Dict[str, Any], ok_statuses: set[str]) -> str:
    payload = result.get("stdout")
    status = payload.get("status") if isinstance(payload, dict) else None
    if result.get("returncode") == 0 and status in ok_statuses:
        return "passed"
    return "failed"


def action_issue_codes(payload: Dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for section in ("errors", "warnings"):
        for item in payload.get(section, []):
            code = item.get("code") if isinstance(item, dict) else None
            if code:
                codes.add(str(code))
    return codes


def build_github_action_report(
    *,
    repo_root: Path,
    roadmap_slug: str = "",
    automation_id: str = "",
    roadmap_path: str = "",
    automation_dir: str = "",
    strict: bool = False,
    allow_warning: Iterable[str] = (),
    privacy_scan: bool = True,
    adapter_check: bool = True,
    release_check: bool = False,
    review_evidence: bool = True,
    report_file: Path,
    live_host_smoke: bool = False,
    live_hosts: Iterable[str] = (),
    python_executable: str = sys.executable,
) -> Dict[str, Any]:
    repo_root = repo_root.expanduser().resolve()
    commands: List[Dict[str, Any]] = []

    if roadmap_slug or automation_id:
        validate_command = [
            python_executable,
            "-m",
            "roadmap_delivery.cli",
            "validate",
            "--repo-root",
            str(repo_root),
            "--json",
        ]
        if roadmap_slug:
            validate_command.extend(["--roadmap-slug", roadmap_slug])
        if automation_id:
            validate_command.extend(["--automation-id", automation_id])
        if strict:
            validate_command.append("--strict")
        for warning in split_action_values(allow_warning):
            validate_command.extend(["--allow-warning", warning])
        validation = run_action_json(validate_command, repo_root)
        validation_status = "passed" if validation["returncode"] == 0 else "failed"
    else:
        validation = {
            "command": None,
            "returncode": None,
            "stdout": {
                "status": "error",
                "errors": [
                    {
                        "code": "missing_validation_target",
                        "message": "Set roadmap-slug or automation-id for offline validation.",
                    }
                ],
                "warnings": [],
            },
            "stderr": "",
        }
        validation_status = "blocked"
    commands.append({"name": "validate", **validation})

    validation_report = validation["stdout"] if isinstance(validation["stdout"], dict) else {}
    validation_errors = validation_report.get("errors", [])
    validation_warnings = validation_report.get("warnings", [])
    errors_count = len(validation_errors) if isinstance(validation_errors, list) else 0
    warnings_count = len(validation_warnings) if isinstance(validation_warnings, list) else 0

    if review_evidence:
        codes = action_issue_codes(validation_report)
        if validation_status == "blocked":
            review_status = "blocked"
        elif codes.intersection({"review_artifact_missing", "review_artifact_schema_error"}):
            review_status = "missing"
        else:
            review_status = "present"
    else:
        review_status = "not-requested"

    if adapter_check:
        adapter = run_action_json(
            [python_executable, "scripts/build_adapters.py", "--repo-root", str(repo_root), "--check", "--json"],
            repo_root,
        )
        adapter_status = command_status(adapter, {"ok"})
        commands.append({"name": "adapter-check", **adapter})
    else:
        adapter_status = "not-requested"

    if privacy_scan:
        privacy = run_action_json(
            [python_executable, "scripts/check_release_privacy.py", "--repo-root", str(repo_root), "--json"],
            repo_root,
        )
        privacy_status = command_status(privacy, {"passed"})
        commands.append({"name": "privacy-scan", **privacy})
    else:
        privacy_status = "not-requested"

    if release_check:
        release = run_action_json(
            [python_executable, "scripts/build_release.py", "--repo-root", str(repo_root), "--check", "--json"],
            repo_root,
        )
        release_status = command_status(release, {"ok"})
        commands.append({"name": "release-check", **release})
    else:
        release_status = "not-requested"

    if live_host_smoke:
        hosts = split_action_values(live_hosts) or ["requested"]
        live_host_status = "skipped"
        skipped_live_hosts = ",".join(f"{host}:reserved-for-later-phase" for host in hosts)
    else:
        live_host_status = "not-requested"
        skipped_live_hosts = ""

    outputs = {
        "validation-status": validation_status,
        "warnings-count": str(warnings_count),
        "errors-count": str(errors_count),
        "review-evidence-status": review_status,
        "adapter-status": adapter_status,
        "privacy-status": privacy_status,
        "release-status": release_status,
        "live-host-status": live_host_status,
        "skipped-live-hosts": skipped_live_hosts,
        "report-file": str(report_file),
    }
    failed = validation_status in {"failed", "blocked"} or any(
        outputs[key] == "failed"
        for key in ("adapter-status", "privacy-status", "release-status", "live-host-status")
    )

    return {
        "schema_version": GITHUB_ACTION_REPORT_SCHEMA_VERSION,
        "github_action_report_schema_version": GITHUB_ACTION_REPORT_SCHEMA_VERSION,
        "command": "github-action",
        "status": "failed" if failed else "passed",
        "repo_root": str(repo_root),
        "roadmap_slug": roadmap_slug,
        "automation_id": automation_id,
        "roadmap_path": roadmap_path,
        "automation_dir": automation_dir,
        "outputs": outputs,
        "commands": commands,
        "host_coverage": build_host_coverage_report(repo_root),
        "errors": [],
    }


def write_github_action_report(report: Dict[str, Any], report_file: Path, report_format: str) -> None:
    report_file.parent.mkdir(parents=True, exist_ok=True)
    if report_format == "json":
        report_file.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return
    lines = [
        f"status: {report.get('status')}",
        f"validation-status: {report['outputs']['validation-status']}",
        f"warnings-count: {report['outputs']['warnings-count']}",
        f"errors-count: {report['outputs']['errors-count']}",
        f"review-evidence-status: {report['outputs']['review-evidence-status']}",
        f"adapter-status: {report['outputs']['adapter-status']}",
        f"privacy-status: {report['outputs']['privacy-status']}",
        f"release-status: {report['outputs']['release-status']}",
        f"live-host-status: {report['outputs']['live-host-status']}",
        "commands:",
    ]
    for item in report.get("commands", []):
        command = item.get("command")
        command_text = " ".join(command) if command else "not run"
        lines.append(f"- {item['name']}: {item.get('returncode')} {command_text}")
    report_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_github_action_outputs(output_file: Path, outputs: Dict[str, str]) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")


def print_github_action_text(report: Dict[str, Any]) -> None:
    print(f"status: {report.get('status')}")
    print(f"report-file: {report['outputs'].get('report-file')}")
    for key, value in report.get("outputs", {}).items():
        print(f"{key}: {value}")


def add_warning(warnings: List[Dict[str, str]], code: str, message: str) -> None:
    warnings.append({"code": code, "message": message})


def report_status(report: Dict[str, Any]) -> str:
    if report.get("errors"):
        return "error"
    if report.get("warnings"):
        return "warning"
    return "ok"


def finding_codes(report: Dict[str, Any], section: str) -> List[str]:
    return [str(item.get("code")) for item in report.get(section, []) if item.get("code")]


def finding_issues(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for section, source in (("errors", "validation_error"), ("warnings", "validation_warning")):
        for item in report.get(section, []):
            code = str(item.get("code") or "unknown")
            issues.append(
                {
                    "code": code,
                    "source": source,
                    "message": str(item.get("message") or ""),
                    "path": item.get("path"),
                    "next_action": next_action_for_issue(code),
                }
            )
    return issues


def next_action_for_issue(code: str) -> str:
    actions = {
        "review_artifact_missing": "Restore the referenced delivered review artifact before advancing.",
        "roadmap_lifecycle_filename_mismatch": "Align roadmap lifecycle filename with roadmap status and current phase.",
        "automation_status_mismatch": "Read back the saved automation status and update state or config before delivery.",
        "verification_evidence_missing": "Rerun required verification and record concrete command evidence.",
        "automation_model_mismatch": "Retarget the saved automation or update approved model policy before implementation.",
        "automation_reasoning_mismatch": "Run with sufficient reasoning or change approved model policy before implementation.",
    }
    return actions.get(code, "Inspect the cited artifact and repair it before phase advancement.")


def relative_path(repo_root: Path, path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def rewrite_toml_string(text: str, key: str, value: str) -> str:
    replacement = f"{key} = {json.dumps(value)}"
    pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(replacement, text)
    suffix = "" if text.endswith("\n") else "\n"
    return f"{text}{suffix}{replacement}\n"


def write_benchmark_automation_config(
    fixture_root: Path,
    fixture_repo: Path,
    automations_dir: Path,
    automation_id: str,
    *,
    status: Optional[str] = None,
) -> None:
    source = fixture_root / "automation-config" / automation_id / "automation.toml"
    if not source.exists():
        raise EvidenceBenchmarkError(f"Benchmark automation config is missing: {source}")
    text = source.read_text(encoding="utf-8")
    text = text.replace('cwds = ["."]', "cwds = [" + json.dumps(str(fixture_repo)) + "]")
    if status:
        text = rewrite_toml_string(text, "status", status)
    target = automations_dir / automation_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "automation.toml").write_text(text, encoding="utf-8")


def run_benchmark_git(repo_root: Path, args: List[str], reason: str) -> None:
    proc = run_git(repo_root, args)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "git command failed"
        raise EvidenceBenchmarkError(f"{reason}: {detail}")


def prepare_benchmark_repo(fixture_root: Path, destination: Path) -> None:
    shutil.copytree(fixture_root, destination)
    run_benchmark_git(destination, ["init", "-b", "codex/demo-roadmap-phase-1"], "Cannot initialize benchmark fixture repo")
    run_benchmark_git(destination, ["add", "."], "Cannot stage benchmark fixture repo")
    run_benchmark_git(
        destination,
        [
            "-c",
            "user.name=Benchmark",
            "-c",
            "user.email=benchmark.invalid",
            "commit",
            "-m",
            "benchmark fixture",
        ],
        "Cannot commit benchmark fixture repo",
    )


def commit_benchmark_repo(repo_root: Path, message: str) -> None:
    run_benchmark_git(repo_root, ["add", "-A"], "Cannot stage benchmark scenario")
    proc = run_git(repo_root, ["diff", "--cached", "--quiet"])
    if proc.returncode == 0:
        return
    run_benchmark_git(
        repo_root,
        [
            "-c",
            "user.name=Benchmark",
            "-c",
            "user.email=benchmark.invalid",
            "commit",
            "-m",
            message,
        ],
        "Cannot commit benchmark scenario",
    )


def demo_state_file(repo_root: Path) -> Path:
    return repo_root / "automation" / "demo_roadmap" / "delivery_state.json"


def mutate_benchmark_scenario(
    scenario_id: str,
    fixture_root: Path,
    fixture_repo: Path,
    automations_dir: Path,
    automation_id: str,
) -> bool:
    if scenario_id == "clean_delivery":
        return False
    if scenario_id == "mismatched_automation_status":
        write_benchmark_automation_config(fixture_root, fixture_repo, automations_dir, automation_id, status="PAUSED")
        return False

    state_path = demo_state_file(fixture_repo)
    state = load_json_object(state_path)
    if scenario_id == "missing_review_artifact":
        last_review = state.get("last_review") if isinstance(state.get("last_review"), dict) else {}
        review_path = resolve_repo_path(fixture_repo, str(last_review.get("file") or ""))
        if review_path and review_path.exists():
            review_path.unlink()
        return True
    if scenario_id == "stale_lifecycle_filename":
        old_path = resolve_repo_path(fixture_repo, str(state.get("roadmap") or ""))
        if not old_path or not old_path.exists():
            raise EvidenceBenchmarkError("Cannot mutate lifecycle scenario because the roadmap path is missing.")
        new_path = old_path.with_name("not_started_demo_roadmap.md")
        old_path.rename(new_path)
        state["roadmap"] = relative_path(fixture_repo, new_path)
        write_json_object(state_path, state)
        return True
    if scenario_id == "insufficient_verification_evidence":
        state["last_verification"] = {
            "phase": state.get("last_delivered_phase"),
            "completed_at": "2026-05-25T08:00:00Z",
            "status": "passed",
            "checks": [],
        }
        write_json_object(state_path, state)
        return True
    raise EvidenceBenchmarkError(f"Unknown benchmark scenario: {scenario_id}")


def evidence_check(check_id: str, passed: bool, *, path: Optional[str] = None, details: str = "") -> Dict[str, Any]:
    return {
        "id": check_id,
        "passed": bool(passed),
        "path": path,
        "details": details,
    }


def benchmark_evidence_checks(
    repo_root: Path,
    validate_report: Dict[str, Any],
    inspect_report: Dict[str, Any],
) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    state_path = Path(str(validate_report.get("state_file") or demo_state_file(repo_root)))
    state = load_json_object(state_path) if state_path.exists() else {}
    state_dir = state_path.parent
    delivery_log = state_dir / "delivery_log.md"
    last_review = state.get("last_review") if isinstance(state.get("last_review"), dict) else {}
    review_path = resolve_repo_path(repo_root, str(last_review.get("file") or "")) if last_review else None
    last_verification = state.get("last_verification") if isinstance(state.get("last_verification"), dict) else {}
    verification_checks = last_verification.get("checks") if isinstance(last_verification, dict) else None
    automation_state = state.get("automation") if isinstance(state.get("automation"), dict) else {}
    state_status = state.get("configured_automation_status") or automation_state.get("status")
    actual_status = inspect_report.get("automation_status")
    expected_branch = inspect_report.get("expected_branch") or state.get("branch")
    current_branch = inspect_report.get("current_branch")
    progress_tracking = validate_report.get("progress_tracking")

    checks.append(evidence_check("delivery_state_present", bool(state), path=relative_path(repo_root, state_path)))
    checks.append(evidence_check("delivery_log_present", delivery_log.exists(), path=relative_path(repo_root, delivery_log)))
    checks.append(
        evidence_check(
            "review_artifact_present",
            bool(review_path and review_path.exists()),
            path=relative_path(repo_root, review_path),
        )
    )
    checks.append(
        evidence_check(
            "review_verdict_delivered",
            str(last_review.get("verdict") or "").lower() == "delivered",
            path=relative_path(repo_root, review_path),
            details=f"verdict={last_review.get('verdict')!r}",
        )
    )
    checks.append(
        evidence_check(
            "verification_checks_recorded",
            isinstance(verification_checks, list)
            and bool(verification_checks)
            and all(str(item.get("status") or "").lower() == "passed" for item in verification_checks if isinstance(item, dict)),
            path=relative_path(repo_root, state_path),
            details=f"checks={len(verification_checks) if isinstance(verification_checks, list) else 0}",
        )
    )
    checks.append(
        evidence_check(
            "branch_matches_state",
            bool(expected_branch and current_branch and expected_branch == current_branch),
            details=f"current={current_branch!r}, expected={expected_branch!r}",
        )
    )
    checks.append(
        evidence_check(
            "model_policy_satisfied",
            not bool(inspect_report.get("model_mismatch")) and bool(inspect_report.get("reasoning_satisfied")),
            details=(
                f"required={inspect_report.get('required_model')}/{inspect_report.get('required_reasoning_effort')}, "
                f"configured={inspect_report.get('configured_automation_model')}/"
                f"{inspect_report.get('configured_automation_reasoning_effort')}"
            ),
        )
    )
    checks.append(
        evidence_check(
            "automation_status_matches_state",
            bool(actual_status and state_status and str(actual_status).upper() == str(state_status).upper()),
            details=f"state={state_status!r}, readback={actual_status!r}",
        )
    )
    checks.append(
        evidence_check(
            "progress_tracking_available",
            isinstance(progress_tracking, dict) and bool(progress_tracking.get("progress_signature")),
            path=relative_path(repo_root, state_path),
        )
    )
    return checks


def evidence_issues(checks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    issue_codes = {
        "review_artifact_present": "review_artifact_missing",
        "verification_checks_recorded": "verification_evidence_missing",
        "automation_status_matches_state": "automation_status_mismatch",
    }
    issues: List[Dict[str, Any]] = []
    for check in checks:
        if check.get("passed"):
            continue
        code = issue_codes.get(str(check.get("id") or ""))
        if not code:
            continue
        issues.append(
            {
                "code": code,
                "source": "evidence_check",
                "message": str(check.get("details") or check.get("id") or ""),
                "path": check.get("path"),
                "next_action": next_action_for_issue(code),
            }
        )
    return issues


def score_evidence_checks(checks: List[Dict[str, Any]]) -> int:
    if not checks:
        return 0
    passed = sum(1 for check in checks if check.get("passed"))
    if passed == len(checks):
        return 2
    if passed:
        return 1
    return 0


def scenario_scores(scenario: Dict[str, Any], issues: List[Dict[str, Any]], checks: List[Dict[str, Any]]) -> Dict[str, int]:
    expected_valid = bool(scenario["expected_valid"])
    invalid_caught = (not expected_valid and bool(issues)) or (expected_valid and not issues)
    recovery_has_next_action = expected_valid or all(issue.get("next_action") for issue in issues)
    return {
        "invalid_advancement_caught": 2 if invalid_caught else 0,
        "evidence_completeness": score_evidence_checks(checks),
        "recovery_path_clarity": 2 if recovery_has_next_action else 0,
        "verification_reproducibility": 2,
    }


def run_evidence_benchmark_scenario(
    scenario: Dict[str, Any],
    *,
    fixture_root: Path,
    roadmap_slug: str,
    automation_id: str,
) -> Dict[str, Any]:
    from . import validation as validation_module

    with tempfile.TemporaryDirectory(prefix=f"roadmap-evidence-{scenario['id']}-") as tmp:
        tmp_path = Path(tmp)
        fixture_repo = tmp_path / "demo-roadmap"
        automations_dir = tmp_path / "home" / ".codex" / "automations"
        prepare_benchmark_repo(fixture_root, fixture_repo)
        write_benchmark_automation_config(fixture_root, fixture_repo, automations_dir, automation_id)
        repo_changed = mutate_benchmark_scenario(str(scenario["id"]), fixture_root, fixture_repo, automations_dir, automation_id)
        if repo_changed:
            commit_benchmark_repo(fixture_repo, f"benchmark scenario {scenario['id']}")

        old_reports_automation_dir = globals()["AUTOMATIONS_DIR"]
        old_validation_automation_dir = validation_module.AUTOMATIONS_DIR
        try:
            globals()["AUTOMATIONS_DIR"] = automations_dir
            validation_module.AUTOMATIONS_DIR = automations_dir
            validate_report = validation_module.validate(fixture_repo, roadmap_slug, automation_id)
            validate_report["status"] = report_status(validate_report)
            inspect_args = argparse.Namespace(repo_root=str(fixture_repo), roadmap_slug=roadmap_slug, automation_id=automation_id)
            inspect_report = inspect(inspect_args)
            inspect_report["status"] = report_status(inspect_report)
        finally:
            globals()["AUTOMATIONS_DIR"] = old_reports_automation_dir
            validation_module.AUTOMATIONS_DIR = old_validation_automation_dir

        checks = benchmark_evidence_checks(fixture_repo, validate_report, inspect_report)
        issues = finding_issues(validate_report) + evidence_issues(checks)
        issue_codes = {str(issue.get("code")) for issue in issues}
        expected_codes = {str(code) for code in scenario.get("expected_issue_codes", [])}
        expectation_met = not issues if scenario["expected_valid"] else bool(issue_codes.intersection(expected_codes))
        scores = scenario_scores(scenario, issues, checks)
        validation_error_codes = finding_codes(validate_report, "errors")
        commands = [
            {
                "command": (
                    "python3 -m roadmap_delivery.cli validate "
                    f"--repo-root {fixture_repo} --roadmap-slug {roadmap_slug} "
                    f"--automation-id {automation_id} --json"
                ),
                "status": "failed" if validate_report.get("errors") else "passed",
                "exit_status": 1 if validate_report.get("errors") else 0,
                "error_codes": validation_error_codes,
                "warning_codes": finding_codes(validate_report, "warnings"),
            },
            {
                "command": (
                    "python3 -m roadmap_delivery.cli inspect "
                    f"--repo-root {fixture_repo} --roadmap-slug {roadmap_slug} "
                    f"--automation-id {automation_id} --json"
                ),
                "status": "failed" if inspect_report.get("errors") else "passed",
                "exit_status": 1 if inspect_report.get("errors") else 0,
                "error_codes": finding_codes(inspect_report, "errors"),
                "warning_codes": finding_codes(inspect_report, "warnings"),
            },
        ]
        return {
            "id": scenario["id"],
            "name": scenario["name"],
            "description": scenario["description"],
            "expected_valid": scenario["expected_valid"],
            "expected_issue_codes": list(scenario["expected_issue_codes"]),
            "expectation_met": expectation_met,
            "validation_caught": bool(validation_error_codes),
            "status": "passed" if expectation_met else "failed",
            "validate": {
                "status": validate_report["status"],
                "error_codes": validation_error_codes,
                "warning_codes": finding_codes(validate_report, "warnings"),
            },
            "inspect": {
                "status": inspect_report["status"],
                "error_codes": finding_codes(inspect_report, "errors"),
                "warning_codes": finding_codes(inspect_report, "warnings"),
                "current_phase": inspect_report.get("current_phase"),
                "current_branch": inspect_report.get("current_branch"),
                "expected_branch": inspect_report.get("expected_branch"),
            },
            "detected_issues": issues,
            "evidence_checks": checks,
            "scores": scores,
            "commands": commands,
            "fixture": {
                "source": str(fixture_root),
                "temporary_repo": str(fixture_repo),
                "temporary_automations_dir": str(automations_dir),
            },
        }


def build_evidence_benchmark(
    repo_root: Path,
    *,
    fixture_root: Optional[Path] = None,
    roadmap_slug: str = "demo-roadmap",
    automation_id: str = "demo-roadmap-delivery",
) -> Dict[str, Any]:
    repo_root = repo_root.expanduser().resolve()
    fixture_root = fixture_root or repo_root / "examples" / "demo-roadmap"
    if not fixture_root.is_absolute():
        fixture_root = repo_root / fixture_root
    fixture_root = fixture_root.resolve()
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []
    if not fixture_root.is_dir():
        errors.append({"code": "benchmark_fixture_missing", "message": f"Fixture root does not exist: {fixture_root}"})
        return {
            "benchmark_schema_version": EVIDENCE_BENCHMARK_SCHEMA_VERSION,
            "status": "failed",
            "repo_root": str(repo_root),
            "fixture_root": str(fixture_root),
            "roadmap_slug": roadmap_slug,
            "automation_id": automation_id,
            "scenarios": [],
            "summary": {},
            "errors": errors,
            "warnings": warnings,
        }

    scenarios: List[Dict[str, Any]] = []
    for scenario in EVIDENCE_BENCHMARK_SCENARIOS:
        try:
            scenarios.append(
                run_evidence_benchmark_scenario(
                    scenario,
                    fixture_root=fixture_root,
                    roadmap_slug=roadmap_slug,
                    automation_id=automation_id,
                )
            )
        except EvidenceBenchmarkError as exc:
            errors.append({"code": "benchmark_scenario_failed", "message": str(exc), "scenario": str(scenario["id"])})

    invalid_scenarios = [scenario for scenario in scenarios if not scenario.get("expected_valid")]
    invalid_caught = [scenario for scenario in invalid_scenarios if scenario.get("detected_issues")]
    validation_caught = [scenario for scenario in invalid_scenarios if scenario.get("validation_caught")]
    clean_warnings = sum(
        len(scenario.get("validate", {}).get("warning_codes", [])) + len(scenario.get("inspect", {}).get("warning_codes", []))
        for scenario in scenarios
        if scenario.get("expected_valid")
    )
    evidence_score = sum(int(scenario.get("scores", {}).get("evidence_completeness", 0)) for scenario in scenarios)
    evidence_max = len(scenarios) * 2
    expectation_failures = [scenario for scenario in scenarios if not scenario.get("expectation_met")]
    if expectation_failures:
        errors.append(
            {
                "code": "benchmark_expectation_failed",
                "message": "One or more benchmark scenarios did not expose the expected evidence.",
            }
        )
    if invalid_scenarios and not validation_caught:
        errors.append(
            {
                "code": "benchmark_validation_caught_none",
                "message": "No invalid-advancement scenario was caught by validation errors.",
            }
        )

    status = "failed" if errors else "passed"
    return {
        "benchmark_schema_version": EVIDENCE_BENCHMARK_SCHEMA_VERSION,
        "status": status,
        "repo_root": str(repo_root),
        "fixture_root": str(fixture_root),
        "roadmap_slug": roadmap_slug,
        "automation_id": automation_id,
        "scenario_count": len(scenarios),
        "scenario_ids": [str(scenario["id"]) for scenario in scenarios],
        "summary": {
            "invalid_scenarios": len(invalid_scenarios),
            "invalid_advancement_caught": len(invalid_caught),
            "invalid_advancement_caught_by_validation": len(validation_caught),
            "evidence_completeness_score": evidence_score,
            "evidence_completeness_max": evidence_max,
            "false_positive_warnings": clean_warnings,
            "verification_reproducible": bool(scenarios) and all(
                command.get("status") in {"passed", "failed"}
                for scenario in scenarios
                for command in scenario.get("commands", [])
            ),
            "claim_boundary": "Results apply only to repository-local fixture scenarios.",
        },
        "metrics": {
            "invalid_advancement_caught": {
                "score": len(invalid_caught),
                "max": len(invalid_scenarios),
                "validation_caught": len(validation_caught),
            },
            "evidence_completeness": {
                "score": evidence_score,
                "max": evidence_max,
            },
            "false_positive_warnings": {
                "score": clean_warnings,
                "max": 0,
            },
        },
        "scenarios": scenarios,
        "errors": errors,
        "warnings": warnings,
    }


def print_benchmark_text(report: Dict[str, Any]) -> None:
    summary = report.get("summary") or {}
    print(f"status: {report.get('status')}")
    print(f"fixture_root: {report.get('fixture_root')}")
    print(f"scenario_count: {report.get('scenario_count', 0)}")
    print(
        "invalid_advancement_caught: "
        f"{summary.get('invalid_advancement_caught')} of {summary.get('invalid_scenarios')}"
    )
    print(
        "invalid_advancement_caught_by_validation: "
        f"{summary.get('invalid_advancement_caught_by_validation')}"
    )
    print(
        "evidence_completeness_score: "
        f"{summary.get('evidence_completeness_score')} of {summary.get('evidence_completeness_max')}"
    )
    print(f"false_positive_warnings: {summary.get('false_positive_warnings')}")
    for scenario in report.get("scenarios", []):
        print(f"- {scenario.get('id')}: {scenario.get('status')}")


def first_finalization_value(state: Optional[Dict[str, Any]], keys: tuple[str, ...]) -> Any:
    if not state:
        return None
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


def final_deep_review_status(state: Optional[Dict[str, Any]]) -> Optional[str]:
    value = first_finalization_value(state, FINAL_DEEP_REVIEW_STATUS_KEYS)
    if value is None:
        return None
    return normalized(value)


def final_deep_review_prompt_prepared(state: Optional[Dict[str, Any]]) -> Optional[bool]:
    value = first_finalization_value(state, FINAL_DEEP_REVIEW_PREPARED_KEYS)
    if isinstance(value, bool):
        return value
    return None


def final_deep_review_waiver_reason(state: Optional[Dict[str, Any]]) -> Optional[str]:
    value = first_finalization_value(state, FINAL_DEEP_REVIEW_WAIVER_REASON_KEYS)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def load_json(path: Path, warnings: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    if not path.exists():
        add_warning(warnings, "missing_state_file", f"State file does not exist: {path}")
        return None
    try:
        return load_json_object(path)
    except JsonObjectError as exc:
        message = str(exc)
        if message.startswith("Invalid JSON"):
            add_warning(warnings, "invalid_state_json", f"State file is invalid JSON: {path}: {message}")
        elif message.startswith("JSON root"):
            add_warning(warnings, "invalid_state_shape", f"State file root is not an object: {path}")
        else:
            raise RuntimeError(f"Cannot read state file {path}: {exc}") from exc
        return None


def load_state_from_candidates(
    repo_root: Path,
    forms: Dict[str, Optional[str]],
    warnings: List[Dict[str, str]],
) -> tuple[Optional[Path], Optional[Dict[str, Any]]]:
    candidates = state_candidates(repo_root, forms)
    for candidate in candidates:
        if candidate.exists():
            return candidate, load_json(candidate, warnings)
    if candidates:
        add_warning(
            warnings,
            "missing_state_file",
            "State file does not exist. Checked: " + ", ".join(str(path) for path in candidates),
        )
        return candidates[0], None
    return None, None


def find_automation_id(forms: Dict[str, Optional[str]], warnings: List[Dict[str, str]]) -> Optional[str]:
    dash = forms["dash"]
    directory = forms["dir"]
    if not dash and not directory:
        return None

    preferred = []
    if dash:
        preferred.append(f"{dash}-delivery")
    if directory:
        preferred.append(f"{directory}-delivery")
    for candidate in preferred:
        if (AUTOMATIONS_DIR / candidate / "automation.toml").exists():
            return candidate

    matches: List[str] = []
    if AUTOMATIONS_DIR.exists():
        needles = [item for item in (dash, directory) if item]
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
        add_warning(
            warnings,
            "multiple_automation_matches",
            "Multiple automation configs match the slug: " + ", ".join(sorted(matches)),
        )
    return None


def warn_lifecycle_filename_drift(
    roadmap_path: Optional[Path],
    state_status: Any,
    current_phase: Any,
    roadmap_status: Any,
    warnings: List[Dict[str, str]],
) -> None:
    if not roadmap_path or not roadmap_path.name.startswith("not_started_"):
        return
    phase = phase_number(current_phase)
    phase_started = phase is not None and int(phase) >= 1
    if normalized(state_status) in LIFECYCLE_ACTIVE_STATE_STATUSES or normalized(roadmap_status) in ACTIVE_STATUSES or phase_started:
        add_warning(
            warnings,
            "roadmap_lifecycle_filename_mismatch",
            f"Active roadmap or Phase 1+ roadmap still uses a not_started_ lifecycle filename: {roadmap_path}",
        )


def read_roadmap_header(roadmap_path: Optional[Path], warnings: List[Dict[str, str]]) -> Dict[str, str]:
    if not roadmap_path or not roadmap_path.exists() or not roadmap_path.is_file():
        return {}
    try:
        text = roadmap_path.read_text(encoding="utf-8")
    except OSError as exc:
        add_warning(warnings, "roadmap_unreadable", f"Cannot read roadmap file: {roadmap_path}: {exc}")
        return {}
    header: Dict[str, str] = {}
    for line in text.splitlines()[:80]:
        match = re.match(r"^(Status|Current phase|Last completed phase|Next action):\s*(.+?)\s*$", line)
        if match:
            header[match.group(1).lower()] = match.group(2)
    return header


def is_complete_state(state: Optional[Dict[str, Any]]) -> bool:
    if not state:
        return False
    state_status = normalized(state.get("status"))
    current_phase = normalized(state.get("current_phase"))
    return (
        bool(state.get("all_phases_complete"))
        or state_status in COMPLETED_STATUSES
        or current_phase in {"complete", "completed", "all-phases-complete"}
    )


def inspect_completion_alert(
    repo_root: Path,
    state: Optional[Dict[str, Any]],
    warnings: List[Dict[str, str]],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "completion_alert_present": False,
        "completion_alert_kind": None,
        "completion_alert_file": None,
    }
    if not state or not is_complete_state(state):
        return result

    last_alert = state.get("last_operator_alert")
    if not isinstance(last_alert, dict):
        add_warning(
            warnings,
            "completed_state_missing_completed_alert",
            "Completed state does not record a completed operator alert.",
        )
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
        add_warning(
            warnings,
            "completed_state_missing_completed_alert",
            f"Completed state records alert kind {kind!r}, not 'completed'.",
        )
    elif alert_path and alert_path.exists() and alert_path.is_file():
        result["completion_alert_present"] = True
    else:
        add_warning(
            warnings,
            "completed_state_missing_completed_alert",
            "Completed state records a completed alert, but the alert file is missing.",
        )
    return result


def find_deep_review_artifact(
    repo_root: Path,
    state_file: Optional[Path],
    forms: Dict[str, Optional[str]],
    state: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if state:
        for key in DEEP_REVIEW_STATE_KEYS:
            value = first_finalization_value(state, (key,))
            if value:
                path = resolve_repo_path(repo_root, str(value))
                return {
                    "path": str(path) if path else str(value),
                    "exists": bool(path and path.exists() and path.is_file()),
                }
        last_verification = state.get("last_verification")
        if isinstance(last_verification, dict) and last_verification.get("deep_review_prompt"):
            value = str(last_verification["deep_review_prompt"])
            path = resolve_repo_path(repo_root, value)
            return {
                "path": str(path) if path else value,
                "exists": bool(path and path.exists() and path.is_file()),
            }

    deep_review_dirs: List[Path] = []
    if state_file is not None:
        deep_review_dirs.append(state_file.parent)
    deep_review_dirs.extend(path for path in automation_dir_candidates(repo_root, forms) if path not in deep_review_dirs)
    for automation_dir in deep_review_dirs:
        review_dir = automation_dir / "reviews"
        if review_dir.is_dir():
            for pattern in ("*deep-review-prompt.md", "*final-deep-review*.md"):
                for path in review_dir.glob(pattern):
                    return {"path": str(path), "exists": path.is_file()}
        for name in DEEP_REVIEW_FILENAMES:
            path = automation_dir / name
            if path.exists():
                return {"path": str(path), "exists": path.is_file()}
    return {"path": None, "exists": False}


def inspect_final_deep_review(
    repo_root: Path,
    state_file: Optional[Path],
    forms: Dict[str, Optional[str]],
    state: Optional[Dict[str, Any]],
    complete: bool,
    warnings: List[Dict[str, str]],
) -> Dict[str, Any]:
    status = final_deep_review_status(state)
    prompt_prepared = final_deep_review_prompt_prepared(state)
    waiver_reason = final_deep_review_waiver_reason(state)
    artifact = find_deep_review_artifact(repo_root, state_file, forms, state)
    result: Dict[str, Any] = {
        "status": status,
        "prompt_prepared": prompt_prepared,
        "prompt": artifact["path"],
        "prompt_exists": artifact["exists"],
        "waived": status == "waived-by-human",
        "waiver_reason": waiver_reason,
    }
    if not complete:
        return result

    if status is not None and status not in FINAL_DEEP_REVIEW_STATUSES:
        add_warning(
            warnings,
            "invalid_final_deep_review_status",
            f"Final deep-review status {status!r} is not one of {sorted(FINAL_DEEP_REVIEW_STATUSES)}.",
        )
    if status == "waived-by-human":
        if not waiver_reason:
            add_warning(
                warnings,
                "final_deep_review_waiver_missing_reason",
                "Final deep review was waived, but no human waiver reason is recorded.",
            )
        return result
    if not artifact["exists"]:
        add_warning(
            warnings,
            "completed_state_missing_final_deep_review_prompt",
            "Completed state does not record an existing final deep-review prompt/review artifact or a human waiver.",
        )
    elif prompt_prepared is None:
        add_warning(
            warnings,
            "final_deep_review_metadata_missing",
            "Completed state has a final deep-review prompt, but does not record final_deep_review_prompt_prepared.",
        )
    if artifact["exists"] and status is None:
        add_warning(
            warnings,
            "final_deep_review_status_missing",
            "Completed state has a final deep-review prompt, but does not record final_deep_review_status.",
        )
    return result


def inspect_model_policy(
    policy_path: Optional[Path],
    state: Optional[Dict[str, Any]],
    automation_data: Dict[str, Any],
    warnings: List[Dict[str, str]],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "policy_path": str(policy_path) if policy_path else None,
        "present": False,
        "required_model": None,
        "required_reasoning_effort": None,
        "base_required_model": None,
        "base_required_reasoning_effort": None,
        "selection_source": None,
        "selection_reason": None,
        "adaptive_policy": None,
        "configured_model": automation_data.get("model") if automation_data else None,
        "configured_reasoning_effort": automation_data.get("reasoning_effort") if automation_data else None,
        "model_mismatch": False,
        "reasoning_mismatch": False,
        "reasoning_satisfied": False,
        "reasoning_over_required": False,
    }
    if not policy_path or not policy_path.exists() or not state:
        return result
    result["present"] = True
    try:
        with policy_path.open("r", encoding="utf-8") as fh:
            policy = json.load(fh)
    except json.JSONDecodeError as exc:
        add_warning(warnings, "invalid_model_policy_json", f"Policy file is invalid JSON: {policy_path}: {exc}")
        return result
    except OSError as exc:
        add_warning(warnings, "model_policy_unreadable", f"Cannot read policy file: {policy_path}: {exc}")
        return result
    if not isinstance(policy, dict):
        add_warning(warnings, "invalid_model_policy_shape", f"Policy file root is not an object: {policy_path}")
        return result
    result["schema_version"] = policy.get("schema_version")
    adaptive_policy = validate_adaptive_model_policy(policy)
    result["adaptive_policy"] = adaptive_policy
    for item in adaptive_policy.get("errors", []):
        add_warning(warnings, str(item.get("code", "invalid_adaptive_policy")), str(item.get("message", "Adaptive model policy is invalid.")))
    if policy.get("schema_version") != 1:
        add_warning(warnings, "unsupported_model_policy_schema", f"Policy schema_version must be 1: {policy_path}")
    defaults = policy.get("defaults") if isinstance(policy.get("defaults"), dict) else {}
    phases = policy.get("phases") if isinstance(policy.get("phases"), dict) else {}
    phase_key = phase_number(state.get("current_phase"))
    if not phase_key and normalized(state.get("current_phase")) in {"complete", "completed", "finalization"}:
        phase_key = "finalization"
    phase_policy = phases.get(phase_key, {}) if phase_key else {}
    if not isinstance(phase_policy, dict):
        phase_policy = {}
    required_model = phase_policy.get("model") or defaults.get("model")
    required_reasoning = phase_policy.get("reasoning_effort") or defaults.get("reasoning_effort")
    selection_source = f"phases.{phase_key}" if phase_key and phase_key in phases else "defaults"
    selection_reason = f"Current phase target resolved from {selection_source}."
    base_required_model = required_model
    base_required_reasoning = required_reasoning
    state_target = adaptive_target_from_state(state, state.get("current_phase"))
    if state_target:
        required_model = state_target.get("model") or required_model
        required_reasoning = state_target.get("reasoning_effort") or required_reasoning
        selection_source = str(state_target.get("source") or "state.last_adaptive_action")
        selection_reason = str(state_target.get("reason") or "Adaptive target recorded in delivery state.")
    configured_model = automation_data.get("model") or state.get("configured_automation_model")
    configured_reasoning = automation_data.get("reasoning_effort") or state.get("configured_automation_reasoning_effort")
    reasoning_satisfied = bool(
        required_reasoning
        and configured_reasoning
        and reasoning_effort_satisfies(configured_reasoning, required_reasoning)
    )
    reasoning_over_required = bool(
        required_reasoning
        and configured_reasoning
        and reasoning_effort_exceeds(configured_reasoning, required_reasoning)
    )
    result.update(
        {
            "required_model": required_model,
            "required_reasoning_effort": required_reasoning,
            "base_required_model": base_required_model,
            "base_required_reasoning_effort": base_required_reasoning,
            "selection_source": selection_source,
            "selection_reason": selection_reason,
            "configured_model": configured_model,
            "configured_reasoning_effort": configured_reasoning,
            "model_mismatch": bool(required_model and configured_model and str(required_model) != str(configured_model)),
            "reasoning_mismatch": bool(required_reasoning and configured_reasoning and not reasoning_satisfied),
            "reasoning_satisfied": reasoning_satisfied,
            "reasoning_over_required": reasoning_over_required,
        }
    )
    if required_reasoning and str(required_reasoning) not in ALLOWED_REASONING_EFFORTS:
        add_warning(warnings, "invalid_required_reasoning_effort", f"Required reasoning effort {required_reasoning!r} is not known.")
    if result["model_mismatch"]:
        add_warning(warnings, "automation_model_mismatch", f"Required model {required_model!r} differs from configured model {configured_model!r}.")
    if result["reasoning_mismatch"]:
        add_warning(warnings, "automation_reasoning_mismatch", f"Required reasoning {required_reasoning!r} exceeds configured reasoning {configured_reasoning!r}.")
    return result


def adaptive_model_decision_summary(state: Optional[Dict[str, Any]], model_policy: Dict[str, Any]) -> Dict[str, Any]:
    if state and isinstance(state.get("last_adaptive_action"), dict):
        return dict(state["last_adaptive_action"])
    return {
        "action": None,
        "run_quality": state.get("last_run_quality") if state else None,
        "target": {
            "model": model_policy.get("required_model"),
            "reasoning_effort": model_policy.get("required_reasoning_effort"),
        },
        "target_changed": False,
        "source": model_policy.get("selection_source"),
        "reason": model_policy.get("selection_reason"),
    }


def lifecycle_matches(repo_root: Path, forms: Dict[str, Optional[str]]) -> List[str]:
    roadmaps_dir = repo_root / "roadmaps"
    if not roadmaps_dir.is_dir():
        return []
    needles = {item for item in (forms["dash"], forms["dir"]) if item}
    matches: List[str] = []
    for path in roadmaps_dir.glob("*.md"):
        normalized_name = path.name.replace("_", "-")
        if any(needle and needle in normalized_name for needle in needles):
            matches.append(str(path))
    return sorted(matches)


def normalize_branch_line(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("* "):
        stripped = stripped[2:].strip()
    return stripped


def inspect(args: argparse.Namespace) -> Dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        raise RuntimeError(f"--repo-root is not a directory: {repo_root}")

    warnings: List[Dict[str, str]] = []
    forms = slug_forms(args.roadmap_slug)
    automation_id = args.automation_id
    if not automation_id:
        automation_id = find_automation_id(forms, warnings)

    automation_status = None
    automation_prompt = ""
    automation_toml = None
    automation_roadmap_references: List[str] = []
    automation_data: Dict[str, Any] = {}
    blocked_remediation_guard = False
    hard_stop_guard = False
    state_resolved_roadmap_prompt = False
    if automation_id:
        automation_toml = AUTOMATIONS_DIR / automation_id / "automation.toml"
        if not automation_toml.exists():
            add_warning(warnings, "missing_automation_config", f"Automation config does not exist: {automation_toml}")
        else:
            automation_data = parse_minimal_toml(automation_toml)
            automation_status = automation_data.get("status")
            automation_prompt = str(automation_data.get("prompt") or "")
            hard_stop_guard = has_hard_stop_guard(automation_prompt)
            blocked_remediation_guard = has_blocked_remediation_guard(automation_prompt)
            state_resolved_roadmap_prompt = has_state_resolved_roadmap_guard(automation_prompt)
            automation_roadmap_references = [
                str(path)
                for path in extract_roadmap_references(
                    automation_prompt,
                    repo_root,
                    require_roadmap_suffix=True,
                )
            ]
            if args.roadmap_slug and forms["dash"] and forms["dir"]:
                if forms["dash"] not in automation_prompt and forms["dir"] not in automation_prompt and forms["dash"] not in automation_id and forms["dir"] not in automation_id:
                    add_warning(
                        warnings,
                        "automation_slug_mismatch",
                        f"Automation {automation_id!r} does not appear to reference roadmap slug {args.roadmap_slug!r}.",
                    )

    if not args.roadmap_slug and automation_prompt:
        match = re.search(r"(?:roadmaps/)?automation/([A-Za-z0-9_-]+)/delivery_state\.json", automation_prompt)
        if match:
            forms = slug_forms(match.group(1))

    state_file = None
    state = None
    if forms["dir"] or forms["dash"]:
        state_file, state = load_state_from_candidates(repo_root, forms, warnings)

    state_slug = state.get("roadmap_slug") if state else None
    if args.roadmap_slug and state_slug:
        requested = args.roadmap_slug.replace("_", "-")
        actual = str(state_slug).replace("_", "-")
        if requested != actual:
            add_warning(
                warnings,
                "roadmap_slug_mismatch",
                f"Requested slug {args.roadmap_slug!r} differs from state roadmap_slug {state_slug!r}",
            )

    state_roadmap = state.get("roadmap") if state else None
    roadmap_path = resolve_repo_path(repo_root, str(state_roadmap)) if state_roadmap else None
    if roadmap_path and not roadmap_path.exists():
        add_warning(warnings, "missing_roadmap_file", f"Roadmap file does not exist: {roadmap_path}")

    for ref in automation_roadmap_references:
        ref_path = Path(ref)
        lifecycle_only_drift = bool(
            roadmap_path
            and state_resolved_roadmap_prompt
            and is_lifecycle_roadmap_sibling(ref_path, roadmap_path)
        )
        if roadmap_path and ref_path != roadmap_path and not ref_path.exists() and not lifecycle_only_drift:
            add_warning(
                warnings,
                "stale_automation_roadmap_path",
                f"Automation prompt references missing roadmap path {ref_path}; state points to {roadmap_path}",
            )
        elif roadmap_path and ref_path != roadmap_path and not lifecycle_only_drift:
            add_warning(
                warnings,
                "automation_roadmap_path_mismatch",
                f"Automation prompt references {ref_path}; state points to {roadmap_path}",
            )

    matches = lifecycle_matches(repo_root, forms)
    if len(matches) > 1:
        add_warning(
            warnings,
            "multiple_matching_roadmap_files",
            "Multiple roadmap lifecycle files match the slug: " + ", ".join(matches),
        )

    branch_proc = run_git(repo_root, ["branch", "--show-current"])
    current_branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else None
    if branch_proc.returncode != 0:
        add_warning(warnings, "git_branch_failed", branch_proc.stderr.strip() or "git branch --show-current failed")

    branch_patterns = []
    if forms["dash"]:
        branch_patterns.append(f"codex/{forms['dash']}*")
    if forms["dir"]:
        branch_patterns.append(f"codex/{forms['dir']}*")
    matching_branches: List[str] = []
    for pattern in unique(branch_patterns):
        proc = run_git(repo_root, ["branch", "--list", pattern])
        if proc.returncode == 0:
            matching_branches.extend(normalize_branch_line(line) for line in proc.stdout.splitlines() if line.strip())
        else:
            add_warning(warnings, "git_branch_list_failed", proc.stderr.strip() or f"git branch --list {pattern} failed")
    matching_branches = sorted(unique(matching_branches))

    status_proc = run_git(repo_root, ["status", "--short"])
    worktree_dirty = False
    if status_proc.returncode == 0:
        worktree_dirty = bool(status_proc.stdout.strip())
        if worktree_dirty:
            add_warning(warnings, "worktree_dirty", "Repository has uncommitted changes.")
    else:
        add_warning(warnings, "git_status_failed", status_proc.stderr.strip() or "git status --short failed")

    state_branch = state.get("branch") if state else None
    if state_branch and current_branch and state_branch != current_branch:
        add_warning(
            warnings,
            "current_branch_mismatch",
            f"Current branch {current_branch!r} differs from state branch {state_branch!r}.",
        )

    state_status = state.get("status") if state else None
    current_phase = state.get("current_phase") if state else None
    state_schema_version = state.get("schema_version") if state else None
    if state is not None and state_schema_version is None:
        add_warning(
            warnings,
            "legacy_delivery_state_schema_version",
            "Delivery state has no schema_version; accepted in legacy compatibility mode.",
        )
    elif state_schema_version not in (None, 1):
        add_warning(warnings, "invalid_delivery_state_schema_version", "Delivery state schema_version must be 1.")
    last_delivered_phase = state.get("last_delivered_phase") if state else None
    blocked_reason = state.get("blocked_reason") if state else None
    roadmap_header = read_roadmap_header(roadmap_path, warnings)
    roadmap_status = roadmap_header.get("status")
    warn_lifecycle_filename_drift(roadmap_path, state_status, current_phase, roadmap_status, warnings)
    state_dir = state_file.parent if state_file else None
    policy_path = state_dir / "phase_model_policy.json" if state_dir else None
    model_policy = inspect_model_policy(policy_path, state, automation_data, warnings)
    progress_report: Dict[str, Any] = {}
    if state_file is not None and state is not None:
        try:
            progress_report = build_run_result(repo_root, state_file, state)
        except ProgressSignatureError as exc:
            add_warning(warnings, "progress_signature_failed", str(exc))
        else:
            for item in progress_report.get("run_log_errors", []):
                line = item.get("line")
                suffix = f" line {line}" if line is not None else ""
                add_warning(warnings, "invalid_run_log_jsonl", f"{item.get('path')}{suffix}: {item.get('message')}")
    blocked_remediation_required = normalized(state_status) == "blocked"
    approval_policy: Optional[Dict[str, Any]] = None
    if state_file is not None and state is not None:
        approval_policy = read_approval_policy(repo_root, state_file, state)
        for item in approval_policy.get("errors", []):
            add_warning(warnings, item.get("code", "invalid_approval_policy"), item.get("message", "Approval policy is invalid."))
    if automation_prompt and not blocked_remediation_guard:
        add_warning(warnings, "automation_prompt_missing_blocked_remediation_guard", "Automation prompt does not include Blocked Remediation Mode.")
    all_phases_complete = is_complete_state(state)
    completion_alert = inspect_completion_alert(repo_root, state, warnings)
    final_deep_review = inspect_final_deep_review(repo_root, state_file, forms, state, all_phases_complete, warnings)
    activation_reconciliation = manual_activation_reconciliation(
        state,
        automation_status,
        model_policy,
        blocked_remediation_guard=blocked_remediation_guard,
        hard_stop_guard=hard_stop_guard,
        complete=all_phases_complete,
    )
    completion_pause_decision = approval_decision_for_pause_context(approval_policy or {}, "completion")
    completion_pause_required = all_phases_complete and str(automation_status).upper() == "ACTIVE"
    automation_should_be_paused = all_phases_complete and str(automation_status).upper() != "PAUSED"
    pause_status = {
        "automation_status": automation_status,
        "completion_pause_required": completion_pause_required,
        "completion_pause_decision": completion_pause_decision,
        "automation_should_be_paused": automation_should_be_paused,
        "last_automation_pause": state.get("last_automation_pause") if state else None,
    }
    if all_phases_complete and str(automation_status).upper() == "ACTIVE":
        add_warning(
            warnings,
            "completed_state_active_automation",
            "State appears complete but the automation is ACTIVE.",
        )

    return {
        "automation_id": automation_id,
        "automation_status": automation_status,
        "automation_toml": str(automation_toml) if automation_toml else None,
        "automation_roadmap_references": automation_roadmap_references,
        "roadmap_path": str(roadmap_path) if roadmap_path else None,
        "state_file": str(state_file) if state_file else None,
        "state_status": state_status,
        "roadmap_status": roadmap_status,
        "state_schema_version": state_schema_version,
        "current_phase": current_phase,
        "last_delivered_phase": last_delivered_phase,
        "blocked_reason": blocked_reason,
        "last_blocker_repair": state.get("last_blocker_repair") if state else None,
        "blocked_remediation_required": blocked_remediation_required,
        "blocked_remediation_guard": blocked_remediation_guard,
        "hard_stop_guard": hard_stop_guard,
        "state_resolved_roadmap_prompt": state_resolved_roadmap_prompt,
        "activation_reconciliation": activation_reconciliation,
        "approval_policy": approval_policy,
        "autonomy_mode": approval_policy.get("approval_mode") if approval_policy else None,
        "allowed_operations": approval_policy.get("approved_operations") if approval_policy else [],
        "required_model": model_policy.get("required_model"),
        "required_reasoning_effort": model_policy.get("required_reasoning_effort"),
        "configured_automation_model": model_policy.get("configured_model"),
        "configured_automation_reasoning_effort": model_policy.get("configured_reasoning_effort"),
        "model_mismatch": model_policy.get("model_mismatch"),
        "reasoning_mismatch": model_policy.get("reasoning_mismatch"),
        "reasoning_satisfied": model_policy.get("reasoning_satisfied"),
        "reasoning_over_required": model_policy.get("reasoning_over_required"),
        "last_run_quality": state.get("last_run_quality") if state else None,
        "adaptive_model_decision": adaptive_model_decision_summary(state, model_policy),
        "run_count": state.get("run_count") if state else None,
        "next_run_count": progress_report.get("run_count"),
        "stalled_run_count": state.get("stalled_run_count") if state else None,
        "next_stalled_run_count": progress_report.get("stalled_run_count"),
        "max_stalled_runs": state.get("max_stalled_runs") if state else None,
        "policy_max_stalled_runs": progress_report.get("max_stalled_runs"),
        "progress_signature": progress_report.get("progress_signature"),
        "previous_progress_signature": progress_report.get("previous_progress_signature"),
        "progress_detected": progress_report.get("progress_detected"),
        "stall_threshold_reached": progress_report.get("threshold_reached"),
        "phase_6_alert_required": progress_report.get("phase_6_alert_required"),
        "run_log_path": progress_report.get("run_log_path"),
        "run_log_entries": progress_report.get("run_log_entries"),
        "run_log_valid": not bool(progress_report.get("run_log_errors")) if progress_report else None,
        "model_policy": model_policy,
        "model_policy_schema_version": model_policy.get("schema_version"),
        "all_phases_complete": all_phases_complete,
        "completion_alert_present": completion_alert["completion_alert_present"],
        "completion_alert_kind": completion_alert["completion_alert_kind"],
        "completion_alert_file": completion_alert["completion_alert_file"],
        "completion_pause_required": completion_pause_required,
        "completion_pause_decision": completion_pause_decision,
        "automation_should_be_paused": automation_should_be_paused,
        "last_automation_pause": state.get("last_automation_pause") if state else None,
        "pause_status": pause_status,
        "final_deep_review_status": final_deep_review["status"],
        "final_deep_review_prompt": final_deep_review["prompt"],
        "final_deep_review_prompt_prepared": final_deep_review["prompt_prepared"],
        "final_deep_review_waived": final_deep_review["waived"],
        "current_branch": current_branch,
        "matching_branches": matching_branches,
        "worktree_dirty": worktree_dirty,
        "deep_review_prompt_exists": final_deep_review["prompt_exists"],
        "warnings": warnings,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect phase-gated roadmap delivery state without mutating files.")
    parser.add_argument("--repo-root", required=True, help="Repository root to inspect.")
    parser.add_argument("--roadmap-slug", help="Roadmap slug, accepting hyphen or underscore form.")
    parser.add_argument("--automation-id", help="Codex automation id under ~/.codex/automations.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    if not args.roadmap_slug and not args.automation_id:
        parser.error("at least one of --roadmap-slug or --automation-id is required")

    try:
        result = inspect(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for key in (
            "automation_id",
            "automation_status",
            "roadmap_path",
            "state_file",
            "roadmap_status",
            "state_status",
            "state_schema_version",
            "current_phase",
            "last_delivered_phase",
            "blocked_reason",
            "blocked_remediation_required",
            "blocked_remediation_guard",
            "hard_stop_guard",
            "activation_reconciliation",
            "approval_policy",
            "autonomy_mode",
            "allowed_operations",
            "required_model",
            "required_reasoning_effort",
            "configured_automation_model",
            "configured_automation_reasoning_effort",
            "model_mismatch",
            "reasoning_mismatch",
            "last_run_quality",
            "adaptive_model_decision",
            "run_count",
            "next_run_count",
            "stalled_run_count",
            "next_stalled_run_count",
            "max_stalled_runs",
            "policy_max_stalled_runs",
            "progress_signature",
            "previous_progress_signature",
            "progress_detected",
            "stall_threshold_reached",
            "phase_6_alert_required",
            "run_log_path",
            "run_log_entries",
            "run_log_valid",
            "model_policy_schema_version",
            "all_phases_complete",
            "completion_alert_present",
            "completion_pause_required",
            "automation_should_be_paused",
            "pause_status",
            "final_deep_review_status",
            "final_deep_review_prompt",
            "final_deep_review_prompt_prepared",
            "final_deep_review_waived",
            "current_branch",
            "worktree_dirty",
            "deep_review_prompt_exists",
        ):
            print(f"{key}: {result.get(key)}")
        if result["warnings"]:
            print("warnings:")
            for warning in result["warnings"]:
                print(f"- {warning['code']}: {warning['message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
