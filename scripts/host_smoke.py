#!/usr/bin/env python3
"""Optional host smoke checks for local roadmap delivery packages."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, Iterable, List, Optional


SCHEMA_VERSION = 1
DEMO_SLUG = "demo-roadmap"
DEMO_AUTOMATION_ID = "demo-roadmap-delivery"
CODEX_REQUIRED_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/phase-loop.md",
    "scripts/inspect_delivery_state.py",
    "scripts/validate_delivery_artifacts.py",
)
CLAUDE_REQUIRED_FILES = (
    ".claude-plugin/plugin.json",
    "README.md",
    "skills/roadmap-delivery-skill/SKILL.md",
    "skills/roadmap-delivery-skill/references/phase-loop.md",
    "agents/reviewer.md",
    "hooks/hooks.json",
    "hooks/roadmap_delivery_safety.py",
)
LIVE_CHECK_NAMES = {
    "codex": "codex_binary_help",
    "claude": "claude_binary_help",
}


def check(name: str, status: str, summary: str, *, reason: Optional[str] = None) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "name": name,
        "status": status,
        "summary": summary,
    }
    if reason:
        item["reason"] = reason
    return item


def sanitize(text: str, replacements: Iterable[tuple[Path, str]]) -> str:
    result = text
    for path, label in replacements:
        result = result.replace(str(path), label)
    return result.strip()


def run_command(
    command: List[str],
    *,
    cwd: Path,
    env: Optional[Dict[str, str]] = None,
    timeout: float,
    replacements: Iterable[tuple[Path, str]],
    input_text: Optional[str] = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=env,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        message = sanitize(str(exc), replacements)
        return subprocess.CompletedProcess(command, 124, "", message)


def load_json_output(proc: subprocess.CompletedProcess[str]) -> Dict[str, Any]:
    try:
        value = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(proc.stderr or proc.stdout or str(exc)) from exc
    if not isinstance(value, dict):
        raise RuntimeError("command did not return a JSON object")
    return value


def copy_demo_repo(repo_root: Path, smoke_root: Path, timeout: float) -> Path:
    source = repo_root / "examples" / "demo-roadmap"
    target = smoke_root / "demo-roadmap"
    shutil.copytree(source, target)
    replacements = ((smoke_root, "$SMOKE_HOME"), (repo_root, "$REPO_ROOT"))
    commands = (
        ["git", "init", "-b", "codex/demo-roadmap-phase-1"],
        ["git", "add", "."],
        [
            "git",
            "-c",
            "user.name=Demo",
            "-c",
            "user.email=demo.invalid",
            "commit",
            "-m",
            "demo fixture",
        ],
    )
    for command in commands:
        proc = run_command(command, cwd=target, timeout=timeout, replacements=replacements)
        if proc.returncode != 0:
            detail = sanitize(proc.stderr or proc.stdout, replacements)
            raise RuntimeError(f"{command[0]} failed while preparing demo fixture: {detail}")
    return target


def prepare_codex_home(repo_root: Path, smoke_root: Path) -> tuple[Path, Path]:
    codex_home = smoke_root / ".codex"
    skill_source = repo_root / "skill" / "roadmap-delivery-skill"
    skill_target = codex_home / "skills" / "roadmap-delivery-skill"
    skill_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill_source, skill_target)
    return codex_home, skill_target


def prepare_demo_automation(codex_home: Path, demo_repo: Path) -> None:
    automation_dir = codex_home / "automations" / DEMO_AUTOMATION_ID
    automation_dir.mkdir(parents=True, exist_ok=True)
    source = demo_repo / "automation-config" / DEMO_AUTOMATION_ID / "automation.toml"
    text = source.read_text(encoding="utf-8")
    text = text.replace('cwds = ["."]', "cwds = [" + json.dumps(str(demo_repo)) + "]")
    (automation_dir / "automation.toml").write_text(text, encoding="utf-8")


def codex_env(repo_root: Path, smoke_root: Path, codex_home: Path) -> Dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(smoke_root / "home")
    env["CODEX_HOME"] = str(codex_home)
    env["AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR"] = str(codex_home / "automations")
    env["PYTHONPYCACHEPREFIX"] = str(smoke_root / "pycache")
    env["PYTHONPATH"] = str(repo_root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    Path(env["HOME"]).mkdir(parents=True, exist_ok=True)
    return env


def run_demo_validation(
    *,
    repo_root: Path,
    smoke_root: Path,
    demo_repo: Path,
    skill_target: Path,
    env: Dict[str, str],
    timeout: float,
    skill_label: str,
) -> Dict[str, Any]:
    replacements = ((smoke_root, "$SMOKE_HOME"), (repo_root, "$REPO_ROOT"))
    commands = (
        [
            sys.executable,
            str(skill_target / "scripts" / "inspect_delivery_state.py"),
            "--repo-root",
            str(demo_repo),
            "--roadmap-slug",
            DEMO_SLUG,
            "--automation-id",
            DEMO_AUTOMATION_ID,
            "--json",
        ],
        [
            sys.executable,
            str(skill_target / "scripts" / "validate_delivery_artifacts.py"),
            "--repo-root",
            str(demo_repo),
            "--roadmap-slug",
            DEMO_SLUG,
            "--automation-id",
            DEMO_AUTOMATION_ID,
            "--strict",
            "--json",
        ],
    )
    reports = []
    for command in commands:
        proc = run_command(command, cwd=demo_repo, env=env, timeout=timeout, replacements=replacements)
        if proc.returncode != 0:
            detail = sanitize(proc.stderr or proc.stdout, replacements)
            return check(
                "demo_fixture_validation",
                "failed",
                "Demo fixture validation command failed.",
                reason=detail or "nonzero_returncode",
            )
        try:
            reports.append(load_json_output(proc))
        except RuntimeError as exc:
            return check(
                "demo_fixture_validation",
                "failed",
                "Demo fixture validation did not return JSON.",
                reason=sanitize(str(exc), replacements),
            )

    inspect_report, validate_report = reports
    if validate_report.get("errors") or validate_report.get("warnings"):
        return check(
            "demo_fixture_validation",
            "failed",
            "Demo fixture validation reported findings.",
            reason=json.dumps(
                {
                    "errors": validate_report.get("errors", []),
                    "warnings": validate_report.get("warnings", []),
                },
                sort_keys=True,
            ),
        )
    if inspect_report.get("current_phase") != "Phase 1 - Add Smoke Checked Command":
        return check(
            "demo_fixture_validation",
            "failed",
            "Demo fixture inspect output did not match the expected phase.",
            reason=str(inspect_report.get("current_phase")),
        )
    return check(
        "demo_fixture_validation",
        "passed",
        f"Installed {skill_label} helper scripts inspected and validated the demo roadmap.",
    )


def run_demo_cli_validation(
    *,
    repo_root: Path,
    smoke_root: Path,
    demo_repo: Path,
    env: Dict[str, str],
    timeout: float,
) -> Dict[str, Any]:
    replacements = ((smoke_root, "$SMOKE_HOME"), (repo_root, "$REPO_ROOT"))
    commands = (
        [
            sys.executable,
            "-m",
            "roadmap_delivery.cli",
            "inspect",
            "--repo-root",
            str(demo_repo),
            "--roadmap-slug",
            DEMO_SLUG,
            "--automation-id",
            DEMO_AUTOMATION_ID,
            "--strict",
            "--json",
        ],
        [
            sys.executable,
            "-m",
            "roadmap_delivery.cli",
            "validate",
            "--repo-root",
            str(demo_repo),
            "--roadmap-slug",
            DEMO_SLUG,
            "--automation-id",
            DEMO_AUTOMATION_ID,
            "--strict",
            "--json",
        ],
    )
    reports = []
    for command in commands:
        proc = run_command(command, cwd=demo_repo, env=env, timeout=timeout, replacements=replacements)
        if proc.returncode != 0:
            detail = sanitize(proc.stderr or proc.stdout, replacements)
            return check(
                "demo_fixture_validation",
                "failed",
                "Demo fixture CLI validation command failed.",
                reason=detail or "nonzero_returncode",
            )
        try:
            reports.append(load_json_output(proc))
        except RuntimeError as exc:
            return check(
                "demo_fixture_validation",
                "failed",
                "Demo fixture CLI validation did not return JSON.",
                reason=sanitize(str(exc), replacements),
            )

    inspect_report, validate_report = reports
    if validate_report.get("errors") or validate_report.get("warnings"):
        return check(
            "demo_fixture_validation",
            "failed",
            "Demo fixture CLI validation reported findings.",
            reason=json.dumps(
                {
                    "errors": validate_report.get("errors", []),
                    "warnings": validate_report.get("warnings", []),
                },
                sort_keys=True,
            ),
        )
    if inspect_report.get("current_phase") != "Phase 1 - Add Smoke Checked Command":
        return check(
            "demo_fixture_validation",
            "failed",
            "Demo fixture inspect output did not match the expected phase.",
            reason=str(inspect_report.get("current_phase")),
        )
    return check(
        "demo_fixture_validation",
        "passed",
        "Repository CLI inspected and validated the demo roadmap with temporary automation readback.",
    )


def run_codex_help(
    *,
    binary_name: str,
    repo_root: Path,
    smoke_root: Path,
    env: Dict[str, str],
    timeout: float,
) -> Dict[str, Any]:
    replacements = ((smoke_root, "$SMOKE_HOME"), (repo_root, "$REPO_ROOT"))
    binary = shutil.which(binary_name)
    if not binary:
        return check(
            "codex_binary_help",
            "skipped",
            "Codex binary is not available on PATH.",
            reason="codex_binary_not_found",
        )
    proc = run_command([binary, "--help"], cwd=repo_root, env=env, timeout=timeout, replacements=replacements)
    if proc.returncode != 0:
        detail = sanitize(proc.stderr or proc.stdout, replacements)
        return check(
            "codex_binary_help",
            "failed",
            "Codex binary help check failed inside the temporary CODEX_HOME.",
            reason=detail or "nonzero_returncode",
        )
    output = (proc.stdout + proc.stderr).strip()
    if not output:
        return check(
            "codex_binary_help",
            "failed",
            "Codex binary help check returned no usage output.",
            reason="empty_help_output",
        )
    return check(
        "codex_binary_help",
        "passed",
        "Codex binary returned help output inside the temporary CODEX_HOME.",
    )


def prepare_claude_plugin(repo_root: Path, smoke_root: Path) -> tuple[Path, Path]:
    plugin_source = repo_root / "dist" / "claude"
    plugin_root = smoke_root / "claude" / "plugins" / "roadmap-delivery"
    plugin_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(plugin_source, plugin_root)
    return plugin_root, plugin_root / "skills" / "roadmap-delivery-skill"


def claude_env(repo_root: Path, smoke_root: Path, plugin_root: Path) -> Dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(smoke_root / "home")
    env["CLAUDE_CONFIG_DIR"] = str(smoke_root / "claude" / "config")
    env["CLAUDE_PLUGIN_DIR"] = str(plugin_root.parent)
    env["AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR"] = str(smoke_root / ".automation-readback" / "automations")
    env["PYTHONPYCACHEPREFIX"] = str(smoke_root / "pycache")
    env["PYTHONPATH"] = str(repo_root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    Path(env["HOME"]).mkdir(parents=True, exist_ok=True)
    Path(env["CLAUDE_CONFIG_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(env["AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR"]).mkdir(parents=True, exist_ok=True)
    return env


def prepare_claude_demo_automation(env: Dict[str, str], demo_repo: Path) -> None:
    automation_dir = Path(env["AUTONOMOUS_ROADMAP_AUTOMATIONS_DIR"]) / DEMO_AUTOMATION_ID
    automation_dir.mkdir(parents=True, exist_ok=True)
    source = demo_repo / "automation-config" / DEMO_AUTOMATION_ID / "automation.toml"
    text = source.read_text(encoding="utf-8")
    text = text.replace('cwds = ["."]', "cwds = [" + json.dumps(str(demo_repo)) + "]")
    (automation_dir / "automation.toml").write_text(text, encoding="utf-8")


def check_claude_manifest(plugin_root: Path) -> Dict[str, Any]:
    manifest_path = plugin_root / ".claude-plugin" / "plugin.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return check(
            "plugin_manifest",
            "failed",
            "Claude plugin manifest could not be parsed.",
            reason=str(exc),
        )
    required = {
        "name": "roadmap-delivery",
        "displayName": "Roadmap Delivery Skill",
        "version": "0.2.0",
        "license": "Apache-2.0",
    }
    mismatches = [key for key, expected in required.items() if manifest.get(key) != expected]
    if mismatches:
        return check(
            "plugin_manifest",
            "failed",
            "Claude plugin manifest does not match the expected package identity.",
            reason=", ".join(mismatches),
        )
    return check("plugin_manifest", "passed", "Claude plugin manifest declares the expected package identity.")


def run_claude_hook_guard(
    *,
    plugin_root: Path,
    repo_root: Path,
    smoke_root: Path,
    env: Dict[str, str],
    timeout: float,
) -> Dict[str, Any]:
    replacements = ((smoke_root, "$SMOKE_HOME"), (repo_root, "$REPO_ROOT"))
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git reset --hard HEAD~1"},
    }
    proc = run_command(
        [sys.executable, str(plugin_root / "hooks" / "roadmap_delivery_safety.py"), "guard-bash"],
        cwd=repo_root,
        env=env,
        timeout=timeout,
        replacements=replacements,
        input_text=json.dumps(payload),
    )
    if proc.returncode != 0:
        detail = sanitize(proc.stderr or proc.stdout, replacements)
        return check("hook_guard", "failed", "Claude hook guard command failed.", reason=detail)
    try:
        output = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return check("hook_guard", "failed", "Claude hook guard did not return JSON.", reason=str(exc))
    decision = output.get("hookSpecificOutput", {})
    if decision.get("permissionDecision") != "ask":
        return check(
            "hook_guard",
            "failed",
            "Claude hook guard did not ask before destructive git.",
            reason=json.dumps(output, sort_keys=True),
        )
    reason = str(decision.get("permissionDecisionReason", ""))
    if "destructive git reset" not in reason:
        return check(
            "hook_guard",
            "failed",
            "Claude hook guard did not identify the destructive git risk.",
            reason=reason or "missing_reason",
        )
    return check(
        "hook_guard",
        "passed",
        "Claude hook guard asks before destructive git; hooks remain reminders, not complete DLP.",
    )


def run_claude_help(
    *,
    binary_name: str,
    repo_root: Path,
    smoke_root: Path,
    env: Dict[str, str],
    timeout: float,
) -> Dict[str, Any]:
    replacements = ((smoke_root, "$SMOKE_HOME"), (repo_root, "$REPO_ROOT"))
    binary = shutil.which(binary_name)
    if not binary:
        return check(
            "claude_binary_help",
            "skipped",
            "Claude binary is not available on PATH.",
            reason="claude_binary_not_found",
        )
    proc = run_command([binary, "--help"], cwd=repo_root, env=env, timeout=timeout, replacements=replacements)
    if proc.returncode != 0:
        detail = sanitize(proc.stderr or proc.stdout, replacements)
        return check(
            "claude_binary_help",
            "failed",
            "Claude binary help check failed with the temporary plugin directory.",
            reason=detail or "nonzero_returncode",
        )
    output = (proc.stdout + proc.stderr).strip()
    if not output:
        return check(
            "claude_binary_help",
            "failed",
            "Claude binary help check returned no usage output.",
            reason="empty_help_output",
        )
    return check(
        "claude_binary_help",
        "passed",
        "Claude binary returned help output with the temporary plugin directory.",
    )


def summarize(host: str, isolated_home: bool, checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {
        "passed": sum(1 for item in checks if item["status"] == "passed"),
        "failed": sum(1 for item in checks if item["status"] == "failed"),
        "skipped": sum(1 for item in checks if item["status"] == "skipped"),
    }
    live_check_name = LIVE_CHECK_NAMES[host]
    live_check = next((item for item in checks if item["name"] == live_check_name), None)
    live_status = live_check["status"] if live_check else "skipped"
    offline_failed = any(item["status"] == "failed" and item["name"] != live_check_name for item in checks)
    offline_status = "failed" if offline_failed else "passed"
    if counts["failed"]:
        status = "failed"
    elif live_status == "skipped":
        status = "skipped"
    else:
        status = "passed"
    return {
        "schema_version": SCHEMA_VERSION,
        "host": host,
        "status": status,
        "offline_status": offline_status,
        "live_status": live_status,
        "isolated_home": isolated_home,
        "active_codex_home_used": False,
        "active_claude_config_used": False,
        "created_real_automation": False,
        "counts": counts,
        "checks": checks,
    }


def run_codex(args: argparse.Namespace) -> Dict[str, Any]:
    repo_root = args.repo_root.resolve()
    checks: List[Dict[str, Any]] = []
    if not args.isolated_home:
        checks.append(
            check(
                "isolated_home",
                "failed",
                "Codex smoke requires --isolated-home to avoid active Codex configuration.",
                reason="isolated_home_required",
            )
        )
        return summarize("codex", False, checks)

    skill_source = repo_root / "skill" / "roadmap-delivery-skill"
    missing = [name for name in CODEX_REQUIRED_FILES if not (skill_source / name).is_file()]
    if missing:
        checks.append(
            check(
                "package_layout",
                "failed",
                "Generated Codex package is missing required files.",
                reason=", ".join(missing),
            )
        )
        return summarize("codex", True, checks)
    checks.append(check("package_layout", "passed", "Generated Codex package layout contains required files."))

    with tempfile.TemporaryDirectory(prefix="roadmap-codex-smoke-") as tmp:
        smoke_root = Path(tmp)
        try:
            codex_home, skill_target = prepare_codex_home(repo_root, smoke_root)
            demo_repo = copy_demo_repo(repo_root, smoke_root, args.timeout)
            prepare_demo_automation(codex_home, demo_repo)
            env = codex_env(repo_root, smoke_root, codex_home)
            checks.append(
                check(
                    "temporary_codex_home",
                    "passed",
                    "Smoke run staged package and automation readback under a temporary CODEX_HOME.",
                )
            )
            checks.append(
                run_demo_validation(
                    repo_root=repo_root,
                    smoke_root=smoke_root,
                    demo_repo=demo_repo,
                    skill_target=skill_target,
                    env=env,
                    timeout=args.timeout,
                    skill_label="Codex",
                )
            )
            checks.append(
                run_codex_help(
                    binary_name=args.codex_binary,
                    repo_root=repo_root,
                    smoke_root=smoke_root,
                    env=env,
                    timeout=args.timeout,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive top-level reporting
            checks.append(
                check(
                    "codex_smoke_setup",
                    "failed",
                    "Codex smoke setup failed before checks completed.",
                    reason=sanitize(str(exc), ((smoke_root, "$SMOKE_HOME"), (repo_root, "$REPO_ROOT"))),
                )
            )
    return summarize("codex", True, checks)


def run_claude(args: argparse.Namespace) -> Dict[str, Any]:
    repo_root = args.repo_root.resolve()
    checks: List[Dict[str, Any]] = []
    if not args.isolated_home:
        checks.append(
            check(
                "isolated_home",
                "failed",
                "Claude smoke requires --isolated-home to avoid active Claude configuration.",
                reason="isolated_home_required",
            )
        )
        return summarize("claude", False, checks)

    plugin_source = repo_root / "dist" / "claude"
    missing = [name for name in CLAUDE_REQUIRED_FILES if not (plugin_source / name).is_file()]
    if missing:
        checks.append(
            check(
                "plugin_layout",
                "failed",
                "Generated Claude plugin package is missing required files.",
                reason=", ".join(missing),
            )
        )
        return summarize("claude", True, checks)
    checks.append(check("plugin_layout", "passed", "Generated Claude plugin package layout contains required files."))
    checks.append(check_claude_manifest(plugin_source))

    with tempfile.TemporaryDirectory(prefix="roadmap-claude-smoke-") as tmp:
        smoke_root = Path(tmp)
        try:
            plugin_root, _skill_target = prepare_claude_plugin(repo_root, smoke_root)
            demo_repo = copy_demo_repo(repo_root, smoke_root, args.timeout)
            env = claude_env(repo_root, smoke_root, plugin_root)
            prepare_claude_demo_automation(env, demo_repo)
            checks.append(
                check(
                    "temporary_claude_plugin_dir",
                    "passed",
                    "Smoke run staged the plugin package under a temporary Claude plugin directory.",
                )
            )
            checks.append(
                run_demo_cli_validation(
                    repo_root=repo_root,
                    smoke_root=smoke_root,
                    demo_repo=demo_repo,
                    env=env,
                    timeout=args.timeout,
                )
            )
            checks.append(
                run_claude_hook_guard(
                    plugin_root=plugin_root,
                    repo_root=repo_root,
                    smoke_root=smoke_root,
                    env=env,
                    timeout=args.timeout,
                )
            )
            checks.append(
                run_claude_help(
                    binary_name=args.claude_binary,
                    repo_root=repo_root,
                    smoke_root=smoke_root,
                    env=env,
                    timeout=args.timeout,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive top-level reporting
            checks.append(
                check(
                    "claude_smoke_setup",
                    "failed",
                    "Claude smoke setup failed before checks completed.",
                    reason=sanitize(str(exc), ((smoke_root, "$SMOKE_HOME"), (repo_root, "$REPO_ROOT"))),
                )
            )
    return summarize("claude", True, checks)


def print_text(report: Dict[str, Any]) -> None:
    print(f"host: {report['host']}")
    print(f"status: {report['status']}")
    print(f"offline_status: {report['offline_status']}")
    print(f"live_status: {report['live_status']}")
    print("checks:")
    for item in report["checks"]:
        line = f"- {item['name']}: {item['status']} - {item['summary']}"
        if item.get("reason"):
            line += f" ({item['reason']})"
        print(line)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("codex", "claude"), required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--isolated-home", action="store_true")
    parser.add_argument("--codex-binary", default="codex")
    parser.add_argument("--claude-binary", default="claude")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.host == "codex":
        report = run_codex(args)
    elif args.host == "claude":
        report = run_claude(args)
    else:  # pragma: no cover - argparse prevents this.
        parser.error(f"unsupported host: {args.host}")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
