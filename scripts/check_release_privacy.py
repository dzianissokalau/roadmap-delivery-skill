#!/usr/bin/env python3
"""Scan release-bound artifacts for obvious privacy and secret leaks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_RELEASE_PATHS = (
    "README.md",
    "SECURITY.md",
    "LICENSE",
    "pyproject.toml",
    "CHANGELOG.md",
    "VERSION",
    "docs",
    "core",
    "schemas",
    "src",
    "scripts",
    "adapters",
    "host-capabilities",
    "config",
    "dist/claude",
    "skill/roadmap-delivery-skill",
)
TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
FORBIDDEN_BUNDLE_PREFIXES = ("automation/", "roadmaps/", ".git/")
FORBIDDEN_BUNDLE_SEGMENTS = {"automation", "roadmaps", ".git", ".codex"}


@dataclass(frozen=True)
class PatternRule:
    code: str
    message: str
    pattern: re.Pattern[str]
    severity: str = "error"
    redact: bool = False


PATTERN_RULES = (
    PatternRule(
        code="local_absolute_path",
        message="Release-bound content contains an unsanitized local absolute path.",
        pattern=re.compile(
            r"(?<![A-Za-z0-9_.-])/(?:Users|home)/[A-Za-z0-9._-]+/[^\s\"'`<>)]*"
        ),
    ),
    PatternRule(
        code="local_absolute_path",
        message="Release-bound content contains an unsanitized Windows user path.",
        pattern=re.compile(
            r"(?<![A-Za-z0-9_.-])[A-Za-z]:\\Users\\[A-Za-z0-9._-]+\\[^\s\"'`<>)]*"
        ),
    ),
    PatternRule(
        code="local_temp_path",
        message="Release-bound content contains an unsanitized local temporary path.",
        pattern=re.compile(r"(?<![A-Za-z0-9_.-])/private/(?:tmp|var/folders)/[^\s\"'`<>)]*"),
    ),
    PatternRule(
        code="private_key",
        message="Release-bound content contains a private key marker.",
        pattern=re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
        redact=True,
    ),
    PatternRule(
        code="aws_access_key",
        message="Release-bound content contains a value shaped like an AWS access key.",
        pattern=re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        redact=True,
    ),
    PatternRule(
        code="github_token",
        message="Release-bound content contains a value shaped like a GitHub token.",
        pattern=re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"),
        redact=True,
    ),
    PatternRule(
        code="github_token",
        message="Release-bound content contains a value shaped like a GitHub fine-grained token.",
        pattern=re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
        redact=True,
    ),
    PatternRule(
        code="openai_api_key",
        message="Release-bound content contains a value shaped like an OpenAI API key.",
        pattern=re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
        redact=True,
    ),
    PatternRule(
        code="generic_secret_assignment",
        message="Release-bound content contains a long token assigned to a secret-like name.",
        pattern=re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*"
            r"[\"'][A-Za-z0-9_./+=-]{24,}[\"']"
        ),
        redact=True,
    ),
)


def safe_release_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"release path must stay inside the repository: {value!r}")
    return path


def should_scan_text(path: str) -> bool:
    suffix = PurePosixPath(path).suffix.lower()
    return suffix in TEXT_SUFFIXES or PurePosixPath(path).name in {"LICENSE"}


def decode_text(data: bytes) -> Optional[str]:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def redacted_match(rule: PatternRule, value: str) -> str:
    if rule.redact:
        return "<redacted>"
    value = re.sub(r"(/(?:Users|home)/)[^/]+/.*", r"\1<user>/...", value)
    value = re.sub(r"([A-Za-z]:\\Users\\)[^\\]+\\.*", r"\1<user>\\...", value)
    if len(value) > 96:
        return f"{value[:93]}..."
    return value


def scan_text(path: str, text: str) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule in PATTERN_RULES:
            for match in rule.pattern.finditer(line):
                findings.append(
                    {
                        "code": rule.code,
                        "severity": rule.severity,
                        "path": path,
                        "line": line_number,
                        "message": rule.message,
                        "match": redacted_match(rule, match.group(0)),
                    }
                )
    return findings


def iter_repo_files(repo_root: Path, release_paths: Sequence[str]) -> Iterable[Tuple[str, bytes]]:
    for raw_path in release_paths:
        rel_path = safe_release_path(raw_path)
        root = repo_root / rel_path
        if not root.exists():
            continue
        if root.is_file():
            if should_scan_text(rel_path.as_posix()):
                yield rel_path.as_posix(), root.read_bytes()
            continue
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
            relative = path.relative_to(repo_root).as_posix()
            if "__pycache__" in path.parts or not should_scan_text(relative):
                continue
            yield relative, path.read_bytes()


def forbidden_bundle_path(name: str) -> Optional[str]:
    path = PurePosixPath(name)
    if name.startswith("/") or ".." in path.parts:
        return "Bundle member path escapes the release archive root."
    if any(name.startswith(prefix) for prefix in FORBIDDEN_BUNDLE_PREFIXES):
        return "Bundle contains repository-local automation, roadmap, or git metadata."
    if any(segment in path.parts for segment in FORBIDDEN_BUNDLE_SEGMENTS):
        return "Bundle contains repository-local automation, roadmap, git, or private Codex metadata."
    return None


def scan_bundle(bundle_path: Path) -> Tuple[int, List[Dict[str, Any]], List[str]]:
    findings: List[Dict[str, Any]] = []
    errors: List[str] = []
    files_scanned = 0
    try:
        archive = tarfile.open(bundle_path, "r:*")
    except (tarfile.TarError, OSError) as exc:
        return 0, findings, [f"Cannot read bundle {bundle_path}: {exc}"]

    with archive:
        for member in archive.getmembers():
            reason = forbidden_bundle_path(member.name)
            if reason:
                findings.append(
                    {
                        "code": "forbidden_bundle_path",
                        "severity": "error",
                        "path": member.name,
                        "line": None,
                        "message": reason,
                        "match": member.name,
                    }
                )
            if not member.isfile() or not should_scan_text(member.name):
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            data = extracted.read()
            text = decode_text(data)
            if text is None:
                continue
            files_scanned += 1
            findings.extend(scan_text(member.name, text))
    return files_scanned, findings, errors


def scan_release(repo_root: Path, release_paths: Sequence[str], bundles: Sequence[str]) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    errors: List[str] = []
    files_scanned = 0

    try:
        for path, data in iter_repo_files(repo_root, release_paths):
            text = decode_text(data)
            if text is None:
                continue
            files_scanned += 1
            findings.extend(scan_text(path, text))
    except (OSError, ValueError) as exc:
        errors.append(str(exc))

    for raw_bundle in bundles:
        bundle_path = Path(raw_bundle)
        if not bundle_path.is_absolute():
            bundle_path = repo_root / bundle_path
        bundle_count, bundle_findings, bundle_errors = scan_bundle(bundle_path)
        files_scanned += bundle_count
        findings.extend(bundle_findings)
        errors.extend(bundle_errors)

    return {
        "schema_version": 1,
        "status": "failed" if findings or errors else "passed",
        "repo_root": str(repo_root),
        "release_paths": list(release_paths),
        "bundles": list(bundles),
        "files_scanned": files_scanned,
        "findings": findings,
        "errors": errors,
    }


def print_text(report: Dict[str, Any]) -> None:
    print(f"status: {report['status']}")
    print(f"files_scanned: {report['files_scanned']}")
    print(f"findings: {len(report['findings'])}")
    for finding in report["findings"]:
        line = f":{finding['line']}" if finding.get("line") else ""
        print(f"- {finding['code']}: {finding['path']}{line}: {finding['message']}")
    print(f"errors: {len(report['errors'])}")
    for error in report["errors"]:
        print(f"- {error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument(
        "--release-path",
        action="append",
        dest="release_paths",
        help="Release-bound path to scan. May be repeated. Defaults to the Codex release bundle inputs.",
    )
    parser.add_argument("--bundle", action="append", default=[], help="Optional tar bundle to scan.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()
    release_paths = args.release_paths or list(DEFAULT_RELEASE_PATHS)
    report = scan_release(repo_root, release_paths, args.bundle)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
