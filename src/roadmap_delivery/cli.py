"""Stable command line interface for roadmap delivery workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import __version__
from .approval import APPROVAL_MODES, read_approval_policy
from .policy import ALLOWED_REASONING_EFFORTS
from .reports import inspect as inspect_state
from .reports import build_evidence_benchmark, print_benchmark_text
from .scaffold import (
    DEFAULT_MAX_STALLED_RUNS,
    ScaffoldOptions,
    apply_scaffold_plan as apply_scaffold_artifact_plan,
    build_scaffold_plan as build_scaffold_artifact_plan,
)
from .state import JsonObjectError, load_json_object
from .validation import parse_allowed_warning_codes, print_text as print_validation_text, validate
from .wizard import apply_wizard_plan, build_wizard_plan, options_from_values


CLI_SCHEMA_VERSION = 1


def _repo_root(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _status(report: Dict[str, Any]) -> str:
    if report.get("errors"):
        return "error"
    if report.get("warnings"):
        return "warning"
    return "ok"


def _with_cli_fields(report: Dict[str, Any], command: str) -> Dict[str, Any]:
    result = dict(report)
    result["cli_schema_version"] = CLI_SCHEMA_VERSION
    result["command"] = command
    result["status"] = _status(result)
    return result


def _strict_failed(report: Dict[str, Any], allowed: set[str]) -> bool:
    return any(str(item.get("code")) not in allowed for item in report.get("warnings", []))


def _print_json(report: Dict[str, Any]) -> None:
    print(json.dumps(report, indent=2, sort_keys=True))


def _print_key_values(report: Dict[str, Any], keys: Iterable[str]) -> None:
    for key in keys:
        print(f"{key}: {report.get(key)}")
    for section in ("errors", "warnings"):
        items = report.get(section) or []
        print(f"{section}: {len(items)}")
        for item in items:
            path = f" [{item['path']}]" if item.get("path") else ""
            print(f"- {item.get('code')}: {item.get('message')}{path}")


def _require_slug_or_automation(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.roadmap_slug and not args.automation_id:
        parser.error("at least one of --roadmap-slug or --automation-id is required")


def run_version(args: argparse.Namespace) -> int:
    report = {
        "cli_schema_version": CLI_SCHEMA_VERSION,
        "command": "version",
        "status": "ok",
        "name": "roadmap-delivery",
        "version": __version__,
    }
    if args.json:
        _print_json(report)
    else:
        print(f"roadmap-delivery {__version__}")
    return 0


def run_inspect(args: argparse.Namespace) -> int:
    _require_slug_or_automation(args.parser, args)
    namespace = argparse.Namespace(
        repo_root=args.repo_root,
        roadmap_slug=args.roadmap_slug,
        automation_id=args.automation_id,
    )
    try:
        report = _with_cli_fields(inspect_state(namespace), "inspect")
    except RuntimeError as exc:
        report = _with_cli_fields(
            {
                "repo_root": str(_repo_root(args.repo_root)),
                "errors": [{"code": "inspect_failed", "message": str(exc)}],
                "warnings": [],
            },
            "inspect",
        )

    if args.json:
        _print_json(report)
    else:
        _print_key_values(
            report,
            (
                "command",
                "status",
                "automation_id",
                "automation_status",
                "roadmap_path",
                "state_file",
                "state_status",
                "current_phase",
                "autonomy_mode",
                "allowed_operations",
                "required_model",
                "required_reasoning_effort",
                "configured_automation_model",
                "configured_automation_reasoning_effort",
                "last_run_quality",
                "adaptive_model_decision",
                "pause_status",
                "current_branch",
                "worktree_dirty",
            ),
        )

    if report.get("errors"):
        return 1
    allowed = parse_allowed_warning_codes(args.allow_warning)
    if args.strict and _strict_failed(report, allowed):
        return 1
    return 0


def run_validate(args: argparse.Namespace) -> int:
    _require_slug_or_automation(args.parser, args)
    repo_root = _repo_root(args.repo_root)
    report = validate(repo_root, args.roadmap_slug, args.automation_id)
    attach_approval_policy_report(report, repo_root)
    report = _with_cli_fields(report, "validate")
    if args.json:
        _print_json(report)
    else:
        print_validation_text(report)

    if report.get("errors"):
        return 1
    allowed = parse_allowed_warning_codes(args.allow_warning)
    if args.strict and _strict_failed(report, allowed):
        return 1
    return 0


def attach_approval_policy_report(report: Dict[str, Any], repo_root: Path) -> None:
    if "approval_policy" in report:
        return
    state_file_value = report.get("state_file")
    if not isinstance(state_file_value, str) or not state_file_value:
        return
    state_file = Path(state_file_value)
    try:
        state = load_json_object(state_file)
    except JsonObjectError:
        return
    approval_report = read_approval_policy(repo_root, state_file, state)
    report["approval_policy"] = approval_report
    report.setdefault("errors", []).extend(approval_report.get("errors", []))


def run_scaffold(args: argparse.Namespace) -> int:
    options = ScaffoldOptions(
        repo_root=_repo_root(args.repo_root),
        roadmap_slug=args.roadmap_slug,
        automation_id=args.automation_id,
        approval_mode=args.approval_mode,
        approval_operations=args.approval_operation,
        max_stalled_runs=args.max_stalled_runs,
        pause_on_completion=args.pause_on_completion,
        pause_on_stall=args.pause_on_stall,
    )
    report = build_scaffold_artifact_plan(options, command="scaffold")
    report["dry_run"] = bool(args.dry_run)
    report["write"] = not bool(args.dry_run)
    if report.get("errors"):
        if args.json:
            _print_json(report)
        else:
            _print_key_values(report, ("command", "status", "dry_run", "repo_root", "roadmap_slug", "automation_id"))
        return 1
    if not args.dry_run:
        apply_scaffold_artifact_plan(report)
    if args.json:
        _print_json(report)
    else:
        _print_key_values(report, ("command", "status", "dry_run", "repo_root", "roadmap_slug", "automation_id"))
        print("approved_operations:")
        for operation in report["approval_policy"]["approved_operations"]:
            print(f"- {operation}")
        print("would_create:")
        for path in report["would_create"]:
            print(f"- {path}")
    allowed = parse_allowed_warning_codes(args.allow_warning)
    if args.strict and _strict_failed(report, allowed):
        return 1
    return 0


def run_wizard(args: argparse.Namespace) -> int:
    options = options_from_values(
        repo_root=_repo_root(args.repo_root),
        roadmap_slug=args.roadmap_slug,
        automation_id=args.automation_id,
        roadmap_title=args.roadmap_title,
        roadmap_path=args.roadmap_path,
        initial_phase=args.initial_phase,
        approval_mode=args.approval_mode,
        approval_operations=args.approval_operation,
        initial_model=args.initial_model,
        reasoning_effort=args.reasoning_effort,
        cadence=args.cadence,
        execution_environment=args.execution_environment,
        host_target=args.host_target,
        branch_prefix=args.branch_prefix,
        max_stalled_runs=args.max_stalled_runs,
        pause_on_completion=args.pause_on_completion,
        pause_on_stall=args.pause_on_stall,
        write=args.write,
        force=args.force,
    )
    report = build_wizard_plan(options)
    if report.get("errors"):
        if args.json:
            _print_json(report)
        else:
            _print_key_values(report, ("command", "status", "mode", "repo_root", "roadmap_slug", "automation_id"))
        return 1
    if args.write:
        apply_wizard_plan(report)
    if args.json:
        _print_json(report)
    else:
        _print_key_values(report, ("command", "status", "mode", "repo_root", "roadmap_slug", "automation_id"))
        print("approval_mode:", report["approval_mode"])
        print("model:", report["model_policy"]["default_model"])
        print("reasoning_effort:", report["model_policy"]["default_reasoning_effort"])
        print("would_create:")
        for path in report["would_create"]:
            print(f"- {path}")
        print("next_commands:")
        for command in report["next_commands"]:
            print(f"- {command}")
    if report.get("errors"):
        return 1
    allowed = parse_allowed_warning_codes(args.allow_warning)
    if args.strict and _strict_failed(report, allowed):
        return 1
    return 0


def run_benchmark(args: argparse.Namespace) -> int:
    repo_root = _repo_root(args.repo_root)
    fixture_root = Path(args.fixture_root).expanduser()
    if not fixture_root.is_absolute():
        fixture_root = repo_root / fixture_root
    report = build_evidence_benchmark(
        repo_root,
        fixture_root=fixture_root,
        roadmap_slug=args.roadmap_slug,
        automation_id=args.automation_id,
    )
    report["cli_schema_version"] = CLI_SCHEMA_VERSION
    report["command"] = "benchmark"

    if args.output:
        output_path = Path(args.output).expanduser()
        if not output_path.is_absolute():
            output_path = repo_root / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        report["output_path"] = str(output_path)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        _print_json(report)
    else:
        print_benchmark_text(report)
    return 0 if report.get("status") == "passed" else 1


def build_package_plan(args: argparse.Namespace) -> Dict[str, Any]:
    repo_root = _repo_root(args.repo_root)
    adapter = args.adapter
    core_paths = [
        repo_root / "core" / "references",
        repo_root / "core" / "templates",
        repo_root / "core" / "prompts",
    ]
    adapter_dir = repo_root / "adapters" / adapter
    output_dir = repo_root / "skill" / f"{adapter}-roadmap-delivery-skill"
    if adapter == "codex":
        output_dir = repo_root / "skill" / "roadmap-delivery-skill"

    required_paths = [*core_paths, output_dir]
    missing = [str(path) for path in required_paths if not path.exists()]
    warnings = []
    if missing:
        warnings.append(
            {
                "code": "package_sources_missing",
                "message": "Some package dry-run inputs are not present.",
                "paths": missing,
            }
        )
    return {
        "cli_schema_version": CLI_SCHEMA_VERSION,
        "command": "package",
        "status": "warning" if warnings else "ok",
        "dry_run": True,
        "repo_root": str(repo_root),
        "adapter": adapter,
        "dry_run_ready": not missing,
        "renderer_ready": adapter_dir.exists() and not missing,
        "adapter_overlay_present": adapter_dir.exists(),
        "planned_adapter_overlay": str(adapter_dir),
        "would_read": [str(path) for path in [*core_paths, adapter_dir]],
        "would_write": str(output_dir),
        "errors": [],
        "warnings": warnings,
    }


def run_package(args: argparse.Namespace) -> int:
    report = build_package_plan(args)
    if args.json:
        _print_json(report)
    else:
        _print_key_values(report, ("command", "status", "dry_run", "repo_root", "adapter", "renderer_ready", "would_write"))
        print("would_read:")
        for path in report["would_read"]:
            print(f"- {path}")
    allowed = parse_allowed_warning_codes(args.allow_warning)
    if args.strict and _strict_failed(report, allowed):
        return 1
    return 0


def add_common_flags(parser: argparse.ArgumentParser, *, require_repo_root: bool = True) -> None:
    parser.add_argument("--repo-root", required=require_repo_root, help="Repository root.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")


def add_state_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--roadmap-slug", help="Roadmap slug, accepting hyphen or underscore form.")
    parser.add_argument("--automation-id", help="Codex automation id under ~/.codex/automations.")


def add_strict_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--strict", action="store_true", help="Return non-zero when warnings are present.")
    parser.add_argument(
        "--allow-warning",
        action="append",
        default=[],
        metavar="CODE",
        help="Warning code to allow under --strict. May be repeated or comma-separated.",
    )


def add_setup_safety_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--max-stalled-runs",
        type=int,
        default=DEFAULT_MAX_STALLED_RUNS,
        help=(
            "Consecutive no-progress runs before blocking and safety-pausing "
            f"the saved automation. Default: {DEFAULT_MAX_STALLED_RUNS}."
        ),
    )
    completion_group = parser.add_mutually_exclusive_group()
    completion_group.add_argument(
        "--pause-on-completion",
        dest="pause_on_completion",
        action="store_true",
        default=None,
        help="Allow completion safety pause. This is the default.",
    )
    completion_group.add_argument(
        "--no-pause-on-completion",
        dest="pause_on_completion",
        action="store_false",
        help="Disable completion safety pause in the generated policy.",
    )
    stall_group = parser.add_mutually_exclusive_group()
    stall_group.add_argument(
        "--pause-on-stall",
        dest="pause_on_stall",
        action="store_true",
        default=None,
        help="Allow stalled-run safety pause. This is the default.",
    )
    stall_group.add_argument(
        "--no-pause-on-stall",
        dest="pause_on_stall",
        action="store_false",
        help="Disable stalled-run safety pause in the generated policy.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="roadmap-delivery", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    version_parser = subparsers.add_parser("version", help="Print the CLI version.")
    version_parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    version_parser.set_defaults(func=run_version, parser=version_parser)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect delivery state without mutating files.")
    add_common_flags(inspect_parser)
    add_state_flags(inspect_parser)
    add_strict_flags(inspect_parser)
    inspect_parser.set_defaults(func=run_inspect, parser=inspect_parser)

    validate_parser = subparsers.add_parser("validate", help="Validate roadmap delivery artifacts.")
    add_common_flags(validate_parser)
    add_state_flags(validate_parser)
    add_strict_flags(validate_parser)
    validate_parser.set_defaults(func=run_validate, parser=validate_parser)

    scaffold_parser = subparsers.add_parser("scaffold", help="Create or plan automation scaffolding.")
    add_common_flags(scaffold_parser)
    scaffold_parser.add_argument("--roadmap-slug", required=True, help="Roadmap slug for the planned automation.")
    scaffold_parser.add_argument("--automation-id", help="Automation id to include in the plan.")
    scaffold_parser.add_argument(
        "--approval-mode",
        default="conservative",
        choices=APPROVAL_MODES,
        help="Approval mode for the generated approval_policy.json.",
    )
    scaffold_parser.add_argument(
        "--approval-operation",
        action="append",
        default=[],
        metavar="OPERATION=allow|deny",
        help="Custom operation decision for --approval-mode custom. May be repeated.",
    )
    add_setup_safety_flags(scaffold_parser)
    scaffold_parser.add_argument("--dry-run", action="store_true", help="Plan files without writing them.")
    add_strict_flags(scaffold_parser)
    scaffold_parser.set_defaults(func=run_scaffold, parser=scaffold_parser)

    wizard_parser = subparsers.add_parser("wizard", help="Plan or write repository-local setup wizard artifacts.")
    add_common_flags(wizard_parser)
    wizard_parser.add_argument("--roadmap-slug", required=True, help="Roadmap slug for generated artifacts.")
    wizard_parser.add_argument("--automation-id", help="Automation id to record in generated artifacts.")
    wizard_parser.add_argument("--roadmap-title", help="Human-readable roadmap title.")
    wizard_parser.add_argument("--roadmap-path", help="Repository-local roadmap path to create or preview.")
    wizard_parser.add_argument("--initial-phase", default="Phase 0 - Scope Confirmation", help="Initial phase name.")
    wizard_parser.add_argument(
        "--approval-mode",
        default="conservative",
        choices=APPROVAL_MODES,
        help="Approval mode for the generated approval_policy.json.",
    )
    wizard_parser.add_argument(
        "--approval-operation",
        action="append",
        default=[],
        metavar="OPERATION=allow|deny",
        help="Custom operation decision for --approval-mode custom. May be repeated.",
    )
    wizard_parser.add_argument("--initial-model", default="gpt-5.5", help="Initial model target to record.")
    wizard_parser.add_argument(
        "--reasoning-effort",
        default="xhigh",
        choices=sorted(ALLOWED_REASONING_EFFORTS),
        help="Initial reasoning effort target to record.",
    )
    wizard_parser.add_argument("--cadence", default="manual", help="Cadence recommendation to record.")
    wizard_parser.add_argument("--execution-environment", default="local", help="Execution environment label to record.")
    wizard_parser.add_argument(
        "--host-target",
        default="codex",
        choices=("codex", "claude", "generic"),
        help="Host target label to record without creating a live automation.",
    )
    wizard_parser.add_argument("--branch-prefix", default="codex/", help="Phase branch prefix to record.")
    add_setup_safety_flags(wizard_parser)
    wizard_mode = wizard_parser.add_mutually_exclusive_group()
    wizard_mode.add_argument("--dry-run", action="store_true", help="Preview files without writing. This is the default.")
    wizard_mode.add_argument("--write", action="store_true", help="Write repository-local artifacts.")
    wizard_parser.add_argument("--force", action="store_true", help="Allow writing into existing artifact paths.")
    add_strict_flags(wizard_parser)
    wizard_parser.set_defaults(func=run_wizard, parser=wizard_parser)

    benchmark_parser = subparsers.add_parser("benchmark", help="Run local evidence benchmark fixture scenarios.")
    add_common_flags(benchmark_parser)
    benchmark_parser.add_argument(
        "--fixture-root",
        default="examples/demo-roadmap",
        help="Repository-local fixture root to copy for scenario runs.",
    )
    benchmark_parser.add_argument("--roadmap-slug", default="demo-roadmap", help="Fixture roadmap slug.")
    benchmark_parser.add_argument("--automation-id", default="demo-roadmap-delivery", help="Fixture automation id.")
    benchmark_parser.add_argument("--output", help="Optional path for a JSON benchmark report.")
    benchmark_parser.set_defaults(func=run_benchmark, parser=benchmark_parser)

    package_parser = subparsers.add_parser("package", help="Plan host package rendering without writing files.")
    add_common_flags(package_parser)
    add_strict_flags(package_parser)
    package_parser.add_argument("--adapter", default="codex", choices=("codex",), help="Host adapter to plan.")
    package_parser.add_argument("--dry-run", action="store_true", help="Accepted for explicit dry-run plans.")
    package_parser.set_defaults(func=run_package, parser=package_parser)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
