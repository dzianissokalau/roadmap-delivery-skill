"""Repository-local scaffold artifact planning for roadmap automations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .approval import (
    approved_operation_names,
    default_approval_policy,
    parse_operation_assignments,
    validate_approval_policy,
)
from .paths import slug_forms
from .policy import ALLOWED_REASONING_EFFORTS


DEFAULT_MODEL = "gpt-5.5"
DEFAULT_REASONING_EFFORT = "xhigh"
DEFAULT_PHASE = "Phase 0 - Scope Confirmation"
DEFAULT_CADENCE = "manual"
DEFAULT_EXECUTION_ENVIRONMENT = "local"
DEFAULT_MAX_STALLED_RUNS = 2


@dataclass(frozen=True)
class ScaffoldOptions:
    repo_root: Path
    roadmap_slug: str
    automation_id: Optional[str] = None
    roadmap_title: Optional[str] = None
    roadmap_path: Optional[str] = None
    initial_phase: str = DEFAULT_PHASE
    approval_mode: str = "conservative"
    approval_operations: Sequence[str] = ()
    initial_model: str = DEFAULT_MODEL
    reasoning_effort: str = DEFAULT_REASONING_EFFORT
    cadence: str = DEFAULT_CADENCE
    execution_environment: str = DEFAULT_EXECUTION_ENVIRONMENT
    host_target: str = "codex"
    branch_prefix: str = "codex/"
    max_stalled_runs: int = DEFAULT_MAX_STALLED_RUNS
    pause_on_completion: Optional[bool] = None
    pause_on_stall: Optional[bool] = None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def status_from_findings(report: Dict[str, Any]) -> str:
    if report.get("errors"):
        return "error"
    if report.get("warnings"):
        return "warning"
    return "ok"


def build_approval_policy(
    mode: str,
    approval_operations: Iterable[str],
    *,
    pause_on_completion: Optional[bool] = None,
    pause_on_stall: Optional[bool] = None,
) -> tuple[Dict[str, Any], List[Dict[str, str]]]:
    operations, errors = parse_operation_assignments(approval_operations)
    if mode != "custom" and operations:
        errors.append(
            {
                "code": "approval_operations_require_custom_mode",
                "message": "--approval-operation may only be used with --approval-mode custom.",
            }
        )
        operations = {}
    policy = default_approval_policy(
        mode,
        operations if mode == "custom" else None,
        pause_on_completion=pause_on_completion,
        pause_on_stall=pause_on_stall,
    )
    errors.extend(validate_approval_policy(policy))
    return policy, errors


def build_phase_model_policy(options: ScaffoldOptions) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "max_stalled_runs": options.max_stalled_runs,
        "notification": {"mode": "alert_file", "fallback": "alert_file"},
        "defaults": {
            "model": options.initial_model,
            "reasoning_effort": options.reasoning_effort,
        },
        "phases": {
            "0": {
                "model": options.initial_model,
                "reasoning_effort": options.reasoning_effort,
            },
            "finalization": {
                "model": options.initial_model,
                "reasoning_effort": options.reasoning_effort,
            },
        },
        "adaptive_model_policy": {
            "enabled": False,
            "escalate_on": [
                "delivered_with_fixes",
                "verification_failed",
                "review_needs_fix",
                "stalled",
                "retarget_failed",
            ],
            "human_gated_qualities": [
                "blocked_human_required",
                "completion_closeout_failed",
            ],
            "deescalate_after_flawless_runs": 0,
            "caps": {
                "allowed_models": [options.initial_model],
                "max_reasoning_effort": options.reasoning_effort,
            },
        },
    }


def _repo_root(value: Path) -> Path:
    return value.expanduser().resolve()


def _safe_relative(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root))
    except ValueError:
        return str(path.resolve())


def _resolve_repo_child(repo_root: Path, value: Optional[str], default: Path, errors: List[Dict[str, str]]) -> Path:
    path = Path(value).expanduser() if value else default
    if not path.is_absolute():
        path = repo_root / path
    resolved = path.resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError:
        errors.append(
            {
                "code": "path_outside_repo_root",
                "message": f"Planned path {resolved} is outside the selected repository root.",
                "path": str(resolved),
            }
        )
    return resolved


def _planned_item(kind: str, path: Path) -> Dict[str, Any]:
    return {"kind": kind, "path": str(path), "exists": path.exists()}


def _title_from_slug(slug: str) -> str:
    return slug.replace("_", "-").replace("-", " ").title()


def validation_commands(repo_root: Path, roadmap_slug: str, automation_id: str) -> List[str]:
    base = [
        "python3 -m roadmap_delivery.cli validate",
        f"--repo-root {json.dumps(str(repo_root))}",
        f"--roadmap-slug {json.dumps(roadmap_slug)}",
        f"--automation-id {json.dumps(automation_id)}",
        "--strict",
        "--allow-warning missing_automation_config",
        "--allow-warning current_branch_name_mismatch",
        "--allow-warning empty_review_dir",
        "--allow-warning worktree_dirty",
        "--allow-warning git_branch_failed",
        "--allow-warning git_status_failed",
        "--json",
    ]
    inspect = [
        "python3 -m roadmap_delivery.cli inspect",
        f"--repo-root {json.dumps(str(repo_root))}",
        f"--roadmap-slug {json.dumps(roadmap_slug)}",
        f"--automation-id {json.dumps(automation_id)}",
        "--json",
    ]
    return [" ".join(base), " ".join(inspect)]


def _path_items(planned_paths: List[Dict[str, Any]], kinds: Iterable[str]) -> List[str]:
    wanted = set(kinds)
    return [item["path"] for item in planned_paths if item.get("kind") in wanted]


def build_scaffold_plan(options: ScaffoldOptions, *, command: str = "scaffold") -> Dict[str, Any]:
    repo_root = _repo_root(options.repo_root)
    forms = slug_forms(options.roadmap_slug)
    slug_dir = forms["dir"] or options.roadmap_slug
    automation_id = options.automation_id or options.roadmap_slug
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []
    if options.reasoning_effort not in ALLOWED_REASONING_EFFORTS:
        errors.append(
            {
                "code": "invalid_reasoning_effort",
                "message": f"Reasoning effort must be one of {sorted(ALLOWED_REASONING_EFFORTS)!r}.",
            }
        )
    if not isinstance(options.max_stalled_runs, int) or isinstance(options.max_stalled_runs, bool) or options.max_stalled_runs < 1:
        errors.append(
            {
                "code": "invalid_max_stalled_runs",
                "message": "max_stalled_runs must be a positive integer.",
            }
        )
    automation_dir = repo_root / "automation" / slug_dir
    roadmap_default = repo_root / "roadmaps" / f"not_started_{slug_dir}_roadmap.md"
    roadmap_path = _resolve_repo_child(repo_root, options.roadmap_path, roadmap_default, errors)
    approval_policy_path = automation_dir / "approval_policy.json"
    approval_policy, approval_errors = build_approval_policy(
        options.approval_mode,
        options.approval_operations,
        pause_on_completion=options.pause_on_completion,
        pause_on_stall=options.pause_on_stall,
    )
    errors.extend(approval_errors)
    model_policy = build_phase_model_policy(options)
    planned_paths = [
        _planned_item("file", roadmap_path),
        _planned_item("directory", automation_dir),
        _planned_item("file", automation_dir / "automation_guide.md"),
        _planned_item("file", approval_policy_path),
        _planned_item("file", automation_dir / "delivery_state.json"),
        _planned_item("file", automation_dir / "delivery_log.md"),
        _planned_item("file", automation_dir / "review_fix_state.json"),
        _planned_item("file", automation_dir / "review_fix_log.md"),
        _planned_item("file", automation_dir / "phase_model_policy.json"),
        _planned_item("file", automation_dir / "automation_run_log.jsonl"),
        _planned_item("directory", automation_dir / "reviews"),
        _planned_item("file", automation_dir / "reviews" / ".gitkeep"),
        _planned_item("directory", automation_dir / "alerts"),
        _planned_item("file", automation_dir / "alerts" / ".gitkeep"),
    ]
    would_create = [item["path"] for item in planned_paths if not item["exists"]]
    automation_artifacts = [
        str(automation_dir / "approval_policy.json"),
        str(automation_dir / "delivery_state.json"),
        str(automation_dir / "review_fix_state.json"),
        str(automation_dir / "phase_model_policy.json"),
        str(automation_dir / "automation_run_log.jsonl"),
        str(automation_dir / "reviews" / ".gitkeep"),
        str(automation_dir / "alerts" / ".gitkeep"),
    ]
    docs_artifacts = [
        str(roadmap_path),
        str(automation_dir / "automation_guide.md"),
        str(automation_dir / "delivery_log.md"),
        str(automation_dir / "review_fix_log.md"),
    ]
    report: Dict[str, Any] = {
        "cli_schema_version": 1,
        "command": command,
        "status": "ok",
        "repo_root": str(repo_root),
        "roadmap_title": options.roadmap_title or _title_from_slug(options.roadmap_slug),
        "roadmap_slug": options.roadmap_slug,
        "roadmap_slug_dir": slug_dir,
        "automation_id": automation_id,
        "automation_dir": str(automation_dir),
        "roadmap_path": str(roadmap_path),
        "roadmap_path_relative": _safe_relative(repo_root, roadmap_path),
        "initial_phase": options.initial_phase,
        "branch": f"{options.branch_prefix}{options.roadmap_slug}-phase-0",
        "approval_mode": approval_policy["approval_mode"],
        "approval_policy": {
            "path": str(approval_policy_path),
            "approval_mode": approval_policy["approval_mode"],
            "approved_operations": approved_operation_names(approval_policy["operations"]),
            "policy": approval_policy,
        },
        "model_policy": {
            "default_model": options.initial_model,
            "default_reasoning_effort": options.reasoning_effort,
            "phase_overrides": model_policy["phases"],
            "policy": model_policy,
        },
        "cadence": options.cadence,
        "execution_environment": options.execution_environment,
        "host_target": options.host_target,
        "planned_paths": planned_paths,
        "planned_create": would_create,
        "planned_directories": _path_items(planned_paths, ("directory",)),
        "would_create": list(would_create),
        "conflicts": [item for item in planned_paths if item["exists"]],
        "created": [],
        "updated": [],
        "artifact_groups": {
            "automation": automation_artifacts,
            "docs": docs_artifacts,
        },
        "preview": {
            "automation": {
                "id": automation_id,
                "directory": str(automation_dir),
                "files": automation_artifacts,
                "live_automation": {
                    "created": False,
                    "edited": False,
                    "activated": False,
                },
            },
            "docs": {
                "roadmap": str(roadmap_path),
                "files": docs_artifacts,
            },
        },
        "live_automation": {
            "created": False,
            "edited": False,
            "activated": False,
            "reason": "Wizard scaffolding is repository-local; saved host automation is a separate explicit step.",
        },
        "next_commands": validation_commands(repo_root, options.roadmap_slug, automation_id),
        "errors": errors,
        "warnings": warnings,
    }
    report["status"] = status_from_findings(report)
    return report


def _write_text(path: Path, content: str, created: List[str], updated: List[str], *, overwrite: bool = False) -> None:
    if path.exists():
        if overwrite:
            path.write_text(content, encoding="utf-8")
            updated.append(str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    created.append(str(path))


def _touch_if_missing(path: Path, created: List[str]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    created.append(str(path))


def _roadmap_text(report: Dict[str, Any], timestamp: str) -> str:
    return "\n".join(
        [
            f"# {report['roadmap_title']} Roadmap",
            "",
            "Status: Not Started",
            f"Current phase: {report['initial_phase']}",
            f"Last updated: {timestamp[:10]}",
            "Next action: Validate generated artifacts, then start Phase 0.",
            "Blocked by: None",
            "",
            f"## {report['initial_phase']}",
            "",
            "### Objective",
            "",
            "Confirm scope and delivery boundaries.",
            "",
            "### Owned Files",
            "",
            "```text",
            "roadmaps/<roadmap-file>.md",
            "automation/<roadmap-slug>/",
            "```",
            "",
            "### Acceptance Criteria",
            "",
            "- Generated automation artifacts validate before delivery starts.",
            "- Live host automation remains a separate explicit setup step.",
            "",
        ]
    )


def _automation_guide_text(report: Dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {report['roadmap_title']} Automation Guide",
            "",
            "Status: Draft",
            f"Roadmap: `{report['roadmap_path_relative']}`",
            f"Roadmap slug: `{report['roadmap_slug']}`",
            f"State file: `automation/{report['roadmap_slug_dir']}/delivery_state.json`",
            f"Delivery log: `automation/{report['roadmap_slug_dir']}/delivery_log.md`",
            f"Review directory: `automation/{report['roadmap_slug_dir']}/reviews`",
            f"Approval policy: `automation/{report['roadmap_slug_dir']}/approval_policy.json`",
            f"Codex automation: `{report['automation_id']}`",
            f"Cadence: {report['cadence']}",
            f"Model: `{report['model_policy']['default_model']}`",
            f"Reasoning effort: `{report['model_policy']['default_reasoning_effort']}`",
            f"Execution environment: {report['execution_environment']}",
            f"Host target: {report['host_target']}",
            "",
            "## Setup Boundary",
            "",
            "These files are repository-local starter artifacts. Creating, editing,",
            "or activating a saved Codex or Claude automation is a separate explicit",
            "operator step.",
            "",
            "## Next Commands",
            "",
            "```bash",
            *report["next_commands"],
            "```",
            "",
        ]
    )


def _delivery_state(report: Dict[str, Any], timestamp: str) -> Dict[str, Any]:
    approval_policy = report["approval_policy"]["policy"]
    approval_path = f"automation/{report['roadmap_slug_dir']}/approval_policy.json"
    return {
        "schema_version": 1,
        "roadmap": report["roadmap_path_relative"],
        "roadmap_slug": report["roadmap_slug"],
        "current_phase": report["initial_phase"],
        "branch": report["branch"],
        "status": "not_started",
        "review_iterations": 0,
        "max_review_iterations": 3,
        "last_verification": None,
        "last_review": None,
        "last_delivered_phase": None,
        "blocked_reason": None,
        "last_blocker_repair": None,
        "approval_policy_path": approval_path,
        "approval_mode": approval_policy["approval_mode"],
        "last_approval_policy_readback": {
            "read_at": timestamp,
            "path": approval_path,
            "status": "valid",
            "approval_mode": approval_policy["approval_mode"],
            "approved_operations": approved_operation_names(approval_policy["operations"]),
            "pause_automation_on_completion": approval_policy.get("pause_automation_on_completion", False),
            "pause_automation_on_stall": approval_policy.get("pause_automation_on_stall", False),
            "fallback_reason": None,
        },
        "required_model": report["model_policy"]["default_model"],
        "required_reasoning_effort": report["model_policy"]["default_reasoning_effort"],
        "configured_automation_model": report["model_policy"]["default_model"],
        "configured_automation_reasoning_effort": report["model_policy"]["default_reasoning_effort"],
        "configured_automation_status": "PLANNED",
        "configured_execution_environment": report["execution_environment"],
        "automation": {
            "id": report["automation_id"],
            "kind": "manual",
            "status": "PLANNED",
            "execution_environment": report["execution_environment"],
            "prompt_roadmap": f"state:automation/{report['roadmap_slug_dir']}/delivery_state.json",
            "prompt_artifact_dir": f"automation/{report['roadmap_slug_dir']}",
            "readback_at": None,
            "prompt_path_strategy": "state_resolved",
        },
        "run_count": 0,
        "stalled_run_count": 0,
        "max_stalled_runs": report["model_policy"]["policy"]["max_stalled_runs"],
        "last_progress_signature": None,
        "last_progress_at": None,
        "last_operator_alert": None,
        "last_automation_pause": None,
        "last_run_quality": None,
        "last_adaptive_action": None,
        "model_history": [],
        "adaptive_escalation_count": 0,
        "adaptive_deescalation_count": 0,
        "adaptive_flawless_streak": 0,
        "auto_advance_after_delivered_review": True,
        "commit_delivered_phase_locally": False,
        "push_to_github": False,
        "all_phases_complete": False,
        "deep_review_prompt": None,
        "final_deep_review_prompt_prepared": False,
        "final_deep_review_prompt_file": None,
        "final_deep_review_status": None,
        "final_deep_review_waiver_reason": None,
        "updated_at": timestamp,
    }


def _delivery_log_text(report: Dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {report['roadmap_title']} Delivery Log",
            "",
            "Status: Draft",
            f"Roadmap: `{report['roadmap_path_relative']}`",
            f"State file: `automation/{report['roadmap_slug_dir']}/delivery_state.json`",
            f"Review directory: `automation/{report['roadmap_slug_dir']}/reviews`",
            f"Approval policy: `automation/{report['roadmap_slug_dir']}/approval_policy.json`",
            f"Codex automation: `{report['automation_id']}`",
            f"Cadence: {report['cadence']}",
            f"Model: `{report['model_policy']['default_model']}`",
            f"Reasoning effort: `{report['model_policy']['default_reasoning_effort']}`",
            f"Execution environment: {report['execution_environment']}",
            "",
            "## Setup Wizard - Pending Validation",
            "",
            "Status: planned",
            "",
            "### Next Action",
            "",
            "- Run the validation and inspection commands from `automation_guide.md`.",
            "- Create or activate saved host automation only as a separate explicit step.",
            "",
        ]
    )


def _review_fix_state(report: Dict[str, Any], timestamp: str) -> Dict[str, Any]:
    return {
        "roadmap": report["roadmap_path_relative"],
        "roadmap_slug": report["roadmap_slug"],
        "current_phase": report["initial_phase"],
        "status": "not_started",
        "review_iterations": 0,
        "max_review_iterations": 3,
        "active_review_file": None,
        "last_verdict": None,
        "last_review_file": None,
        "last_delivered_phase": None,
        "blocked_reason": None,
        "updated_at": timestamp,
    }


def apply_scaffold_plan(report: Dict[str, Any]) -> None:
    timestamp = utc_now()
    automation_dir = Path(str(report["automation_dir"]))
    roadmap_path = Path(str(report["roadmap_path"]))
    created: List[str] = []
    updated: List[str] = []
    overwrite = bool(report.get("force"))
    for directory in (automation_dir, automation_dir / "reviews", automation_dir / "alerts"):
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            created.append(str(directory))
    _write_text(roadmap_path, _roadmap_text(report, timestamp), created, updated, overwrite=overwrite)
    _write_text(automation_dir / "automation_guide.md", _automation_guide_text(report), created, updated, overwrite=overwrite)
    _write_text(
        automation_dir / "approval_policy.json",
        json.dumps(report["approval_policy"]["policy"], indent=2, sort_keys=False) + "\n",
        created,
        updated,
        overwrite=overwrite,
    )
    _write_text(
        automation_dir / "delivery_state.json",
        json.dumps(_delivery_state(report, timestamp), indent=2, sort_keys=False) + "\n",
        created,
        updated,
        overwrite=overwrite,
    )
    _write_text(automation_dir / "delivery_log.md", _delivery_log_text(report), created, updated, overwrite=overwrite)
    _write_text(
        automation_dir / "review_fix_state.json",
        json.dumps(_review_fix_state(report, timestamp), indent=2, sort_keys=False) + "\n",
        created,
        updated,
        overwrite=overwrite,
    )
    _write_text(
        automation_dir / "review_fix_log.md",
        f"# {report['roadmap_title']} Review/Fix Log\n",
        created,
        updated,
        overwrite=overwrite,
    )
    _write_text(
        automation_dir / "phase_model_policy.json",
        json.dumps(report["model_policy"]["policy"], indent=2, sort_keys=False) + "\n",
        created,
        updated,
        overwrite=overwrite,
    )
    _write_text(automation_dir / "automation_run_log.jsonl", "", created, updated, overwrite=overwrite)
    _touch_if_missing(automation_dir / "reviews" / ".gitkeep", created)
    _touch_if_missing(automation_dir / "alerts" / ".gitkeep", created)
    report["created"] = created
    report["updated"] = updated
    report["would_create"] = [path for path in report.get("would_create", []) if path not in set(created)]
