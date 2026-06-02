"""Setup wizard command contract for repository-local roadmap automation files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional, Sequence

from .scaffold import ScaffoldOptions, apply_scaffold_plan, build_scaffold_plan
from .reports import inspect as inspect_state
from .validation import validate


EXPECTED_SETUP_WARNINGS = [
    "missing_automation_config",
    "current_branch_name_mismatch",
    "empty_review_dir",
    "worktree_dirty",
    "git_branch_failed",
    "git_status_failed",
]


@dataclass(frozen=True)
class WizardOptions:
    scaffold: ScaffoldOptions
    write: bool = False
    force: bool = False


def build_wizard_plan(options: WizardOptions) -> Dict[str, Any]:
    report = build_scaffold_plan(options.scaffold, command="wizard")
    report["dry_run"] = not options.write
    report["write"] = options.write
    report["mode"] = "write" if options.write else "dry-run"
    report["force"] = options.force
    report["status"] = "planned" if not report.get("errors") else "error"
    report["setup_choices"] = {
        "roadmap_slug": report["roadmap_slug"],
        "automation_id": report["automation_id"],
        "approval_mode": report["approval_mode"],
        "default_model": report["model_policy"]["default_model"],
        "default_reasoning_effort": report["model_policy"]["default_reasoning_effort"],
        "cadence": report["cadence"],
        "execution_environment": report["execution_environment"],
        "host_target": report["host_target"],
        "max_stalled_runs": report["model_policy"]["policy"]["max_stalled_runs"],
        "pause_automation_on_completion": report["approval_policy"]["policy"].get("pause_automation_on_completion"),
        "pause_automation_on_stall": report["approval_policy"]["policy"].get("pause_automation_on_stall"),
    }
    report["validation"] = {
        "next_commands": report["next_commands"],
        "expected_setup_warnings": list(EXPECTED_SETUP_WARNINGS),
    }
    report["readback"] = {
        "ran": False,
        "status": "not_run",
        "reason": "Readback runs only after --write creates repository-local artifacts.",
    }
    if options.write and report.get("conflicts") and not options.force:
        report.setdefault("errors", []).append(
            {
                "code": "wizard_existing_artifacts",
                "message": "Wizard write mode refuses to overwrite existing roadmap or automation artifacts without --force.",
                "paths": [item["path"] for item in report["conflicts"]],
            }
        )
    if report.get("errors"):
        report["status"] = "error"
    return report


def _compact_findings(items: Any) -> list[Dict[str, Any]]:
    findings: list[Dict[str, Any]] = []
    if not isinstance(items, list):
        return findings
    for item in items:
        if not isinstance(item, dict):
            continue
        compact: Dict[str, Any] = {
            "code": item.get("code"),
            "message": item.get("message"),
        }
        if item.get("path"):
            compact["path"] = item.get("path")
        findings.append(compact)
    return findings


def _summary_status(errors: list[Dict[str, Any]], warnings: list[Dict[str, Any]]) -> str:
    if errors:
        return "error"
    if warnings:
        return "warning"
    return "ok"


def _readback_summary(report: Dict[str, Any], *, keys: Sequence[str] = ()) -> Dict[str, Any]:
    errors = _compact_findings(report.get("errors"))
    warnings = _compact_findings(report.get("warnings"))
    summary: Dict[str, Any] = {
        "status": _summary_status(errors, warnings),
        "errors": errors,
        "warnings": warnings,
        "warning_codes": [item["code"] for item in warnings if item.get("code")],
        "unexpected_warning_codes": [
            item["code"]
            for item in warnings
            if item.get("code") and item.get("code") not in EXPECTED_SETUP_WARNINGS
        ],
    }
    for key in keys:
        if key in report:
            summary[key] = report[key]
    return summary


def build_wizard_readback(report: Dict[str, Any]) -> Dict[str, Any]:
    repo_root = Path(str(report["repo_root"]))
    roadmap_slug = str(report["roadmap_slug"])
    automation_id = str(report["automation_id"])
    validation_report = validate(repo_root, roadmap_slug, automation_id)
    inspection_report: Dict[str, Any]
    try:
        inspection_report = inspect_state(
            SimpleNamespace(
                repo_root=str(repo_root),
                roadmap_slug=roadmap_slug,
                automation_id=automation_id,
            )
        )
    except RuntimeError as exc:
        inspection_report = {
            "errors": [{"code": "wizard_inspect_failed", "message": str(exc)}],
            "warnings": [],
        }

    validate_summary = _readback_summary(
        validation_report,
        keys=(
            "state_file",
            "roadmap_path",
            "state_status",
            "state_current_phase",
            "current_branch",
            "expected_branch",
            "worktree_dirty",
        ),
    )
    inspect_summary = _readback_summary(
        inspection_report,
        keys=(
            "state_file",
            "roadmap_path",
            "state_status",
            "current_phase",
            "current_branch",
            "worktree_dirty",
        ),
    )
    combined_errors = validate_summary["errors"] + inspect_summary["errors"]
    combined_warnings = validate_summary["warnings"] + inspect_summary["warnings"]
    return {
        "ran": True,
        "status": _summary_status(combined_errors, combined_warnings),
        "expected_setup_warnings": list(EXPECTED_SETUP_WARNINGS),
        "validate": validate_summary,
        "inspect": inspect_summary,
    }


def apply_wizard_plan(report: Dict[str, Any]) -> None:
    apply_scaffold_plan(report)
    report["readback"] = build_wizard_readback(report)
    readback_errors = report["readback"]["validate"]["errors"] + report["readback"]["inspect"]["errors"]
    if readback_errors:
        report.setdefault("errors", []).append(
            {
                "code": "wizard_readback_failed",
                "message": "Wizard wrote repository-local artifacts, but validate or inspect readback reported errors.",
                "readback_error_codes": [item["code"] for item in readback_errors if item.get("code")],
            }
        )
    if not report.get("errors"):
        report["status"] = "written"
        report["dry_run"] = False
        report["write"] = True
        report["mode"] = "write"
        report["conflicts"] = []
    else:
        report["status"] = "error"


def options_from_values(
    *,
    repo_root: Path,
    roadmap_slug: str,
    automation_id: Optional[str] = None,
    roadmap_title: Optional[str] = None,
    roadmap_path: Optional[str] = None,
    initial_phase: str,
    approval_mode: str,
    approval_operations: Sequence[str],
    initial_model: str,
    reasoning_effort: str,
    cadence: str,
    execution_environment: str,
    host_target: str,
    branch_prefix: str,
    max_stalled_runs: int,
    pause_on_completion: Optional[bool],
    pause_on_stall: Optional[bool],
    write: bool,
    force: bool = False,
) -> WizardOptions:
    return WizardOptions(
        scaffold=ScaffoldOptions(
            repo_root=repo_root,
            roadmap_slug=roadmap_slug,
            automation_id=automation_id,
            roadmap_title=roadmap_title,
            roadmap_path=roadmap_path,
            initial_phase=initial_phase,
            approval_mode=approval_mode,
            approval_operations=approval_operations,
            initial_model=initial_model,
            reasoning_effort=reasoning_effort,
            cadence=cadence,
            execution_environment=execution_environment,
            host_target=host_target,
            branch_prefix=branch_prefix,
            max_stalled_runs=max_stalled_runs,
            pause_on_completion=pause_on_completion,
            pause_on_stall=pause_on_stall,
        ),
        write=write,
        force=force,
    )
