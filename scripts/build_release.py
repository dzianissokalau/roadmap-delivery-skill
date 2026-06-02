#!/usr/bin/env python3
"""Build deterministic local release artifacts for roadmap delivery."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
CODEX_SKILL_ROOT = "skill/roadmap-delivery-skill"
CLAUDE_PLUGIN_ROOT = "dist/claude"
SOURCE_PATHS = (
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
    CLAUDE_PLUGIN_ROOT,
    CODEX_SKILL_ROOT,
)
CLI_SOURCE_PATHS = (
    "README.md",
    "LICENSE",
    "pyproject.toml",
    "CHANGELOG.md",
    "VERSION",
    "src",
)
SCHEMA_PATHS = (
    "VERSION",
    "schemas",
)
RELEASE_VERIFICATION_COMMANDS = (
    "python3 scripts/build_adapters.py --check",
    "python3 scripts/build_release.py --check --json",
    "python3 scripts/check_release_privacy.py --repo-root .",
    "python3 -m unittest tests.test_install_smoke -v",
)


class ReleaseBuildError(RuntimeError):
    """Raised when release artifacts cannot be built safely."""


@dataclass(frozen=True)
class ArtifactSpec:
    kind: str
    filename: str
    prefix: str
    paths: Sequence[str]
    strip_prefix: Optional[str] = None


@dataclass(frozen=True)
class BuiltArtifact:
    kind: str
    filename: str
    path: Path
    sha256: str
    size: int

    def as_report(self, *, include_path: bool) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "kind": self.kind,
            "filename": self.filename,
            "sha256": self.sha256,
            "size": self.size,
        }
        if include_path:
            row["path"] = str(self.path)
        return row


def safe_relative_path(value: str, *, field: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not value:
        raise ReleaseBuildError(f"{field} must stay inside the repository: {value!r}")
    return path


def read_version(repo_root: Path) -> str:
    version_path = repo_root / "VERSION"
    try:
        version = version_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ReleaseBuildError(f"Cannot read VERSION: {exc}") from exc
    if not VERSION_RE.match(version):
        raise ReleaseBuildError(f"VERSION must be semantic version text, got {version!r}")
    return version


def validate_release_inputs(repo_root: Path, version: str) -> None:
    missing = [path for path in SOURCE_PATHS if not (repo_root / path).exists()]
    if missing:
        raise ReleaseBuildError(f"Release inputs are missing: {', '.join(missing)}")

    release_notes = repo_root / release_notes_path(version)
    if not release_notes.is_file():
        raise ReleaseBuildError(f"Release notes are missing for {version}: {release_notes.relative_to(repo_root)}")
    release_notes_text = release_notes.read_text(encoding="utf-8")
    required_note_sections = (
        "## Release Artifacts",
        "## Local Verification",
        "## Limitations",
        "## Publication Boundary",
    )
    missing_note_sections = [section for section in required_note_sections if section not in release_notes_text]
    if missing_note_sections:
        raise ReleaseBuildError(
            "Release notes must be the source of truth for artifacts, verification, limitations, and publication: "
            + ", ".join(missing_note_sections)
        )

    changelog = (repo_root / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## {version} " not in changelog:
        raise ReleaseBuildError(f"CHANGELOG.md does not contain an entry for {version}")
    if "Compatibility Notes" not in changelog:
        raise ReleaseBuildError("CHANGELOG.md must identify compatibility notes")

    skill_root = repo_root / CODEX_SKILL_ROOT
    for required in ("SKILL.md", "references/phase-loop.md", "scripts/validate_delivery_artifacts.py"):
        if not (skill_root / required).is_file():
            raise ReleaseBuildError(f"Codex skill package is missing {required}")


def artifact_specs(version: str) -> List[ArtifactSpec]:
    return [
        ArtifactSpec(
            kind="source_archive",
            filename=f"roadmap-delivery-{version}-source.tar.gz",
            prefix=f"roadmap-delivery-{version}",
            paths=SOURCE_PATHS,
        ),
        ArtifactSpec(
            kind="codex_skill_package",
            filename=f"roadmap-delivery-codex-skill-{version}.tar.gz",
            prefix=f"roadmap-delivery-codex-skill-{version}",
            paths=(CODEX_SKILL_ROOT,),
            strip_prefix=CODEX_SKILL_ROOT,
        ),
        ArtifactSpec(
            kind="claude_plugin_package",
            filename=f"roadmap-delivery-claude-plugin-{version}.tar.gz",
            prefix=f"roadmap-delivery-claude-plugin-{version}",
            paths=(CLAUDE_PLUGIN_ROOT,),
            strip_prefix=CLAUDE_PLUGIN_ROOT,
        ),
        ArtifactSpec(
            kind="schema_bundle",
            filename=f"roadmap-delivery-schemas-{version}.tar.gz",
            prefix=f"roadmap-delivery-schemas-{version}",
            paths=SCHEMA_PATHS,
        ),
        ArtifactSpec(
            kind="cli_source_package",
            filename=f"roadmap-delivery-cli-{version}.tar.gz",
            prefix=f"roadmap-delivery-cli-{version}",
            paths=CLI_SOURCE_PATHS,
        ),
    ]


def generic_artifact_filename(version: str) -> str:
    return f"roadmap-delivery-generic-markdown-pack-{version}.tar.gz"


def release_notes_path(version: str) -> str:
    return f"docs/release-notes-{version}.md"


def should_skip_file(path: Path) -> bool:
    generated_metadata = any(part.endswith((".egg-info", ".dist-info")) for part in path.parts)
    return path.name == ".DS_Store" or path.suffix == ".pyc" or "__pycache__" in path.parts or generated_metadata


def iter_release_files(repo_root: Path, paths: Sequence[str]) -> Iterable[Tuple[Path, Path]]:
    for raw_path in paths:
        rel_root = safe_relative_path(raw_path, field="release path")
        root = repo_root / rel_root
        if not root.exists():
            raise ReleaseBuildError(f"Release path does not exist: {raw_path}")
        if root.is_symlink():
            raise ReleaseBuildError(f"Release path must not be a symlink: {raw_path}")
        if root.is_file():
            if not should_skip_file(root):
                yield rel_root, root
            continue
        for candidate in sorted(path for path in root.rglob("*") if path.is_file()):
            if candidate.is_symlink():
                raise ReleaseBuildError(f"Release file must not be a symlink: {candidate}")
            if should_skip_file(candidate):
                continue
            yield candidate.relative_to(repo_root), candidate


def archive_name(spec: ArtifactSpec, rel_path: Path) -> str:
    if spec.strip_prefix:
        strip = PurePosixPath(spec.strip_prefix)
        rel_posix = PurePosixPath(rel_path.as_posix())
        try:
            rel_posix = rel_posix.relative_to(strip)
        except ValueError as exc:
            raise ReleaseBuildError(f"{rel_path} is outside strip prefix {spec.strip_prefix}") from exc
    else:
        rel_posix = PurePosixPath(rel_path.as_posix())
    name = PurePosixPath(spec.prefix) / rel_posix
    if name.is_absolute() or ".." in name.parts:
        raise ReleaseBuildError(f"Archive member escapes release root: {name}")
    return name.as_posix()


def normalized_mode(path: Path) -> int:
    return 0o755 if os.access(path, os.X_OK) else 0o644


def write_tar_gz(repo_root: Path, output_path: Path, spec: ArtifactSpec) -> BuiltArtifact:
    files = list(iter_release_files(repo_root, spec.paths))
    if not files:
        raise ReleaseBuildError(f"No files selected for {spec.kind}")

    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as archive:
        for rel_path, source_path in files:
            data = source_path.read_bytes()
            info = tarfile.TarInfo(archive_name(spec, rel_path))
            info.size = len(data)
            info.mtime = 0
            info.mode = normalized_mode(source_path)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(data))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as raw_file:
        with gzip.GzipFile(fileobj=raw_file, mode="wb", mtime=0) as gzip_file:
            gzip_file.write(tar_buffer.getvalue())
    return describe_artifact(spec.kind, output_path)


def iter_directory_files(source_root: Path) -> Iterable[Tuple[Path, Path]]:
    if not source_root.is_dir():
        raise ReleaseBuildError(f"Release artifact source is not a directory: {source_root}")
    if source_root.is_symlink():
        raise ReleaseBuildError(f"Release artifact source must not be a symlink: {source_root}")
    for candidate in sorted(path for path in source_root.rglob("*") if path.is_file()):
        if candidate.is_symlink():
            raise ReleaseBuildError(f"Release file must not be a symlink: {candidate}")
        if should_skip_file(candidate):
            continue
        yield candidate.relative_to(source_root), candidate


def write_directory_tar_gz(source_root: Path, output_path: Path, *, kind: str, prefix: str) -> BuiltArtifact:
    files = list(iter_directory_files(source_root))
    if not files:
        raise ReleaseBuildError(f"No files selected for {kind}")

    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as archive:
        for rel_path, source_path in files:
            data = source_path.read_bytes()
            archive_member = PurePosixPath(prefix) / PurePosixPath(rel_path.as_posix())
            if archive_member.is_absolute() or ".." in archive_member.parts:
                raise ReleaseBuildError(f"Archive member escapes release root: {archive_member}")
            info = tarfile.TarInfo(archive_member.as_posix())
            info.size = len(data)
            info.mtime = 0
            info.mode = normalized_mode(source_path)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(data))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as raw_file:
        with gzip.GzipFile(fileobj=raw_file, mode="wb", mtime=0) as gzip_file:
            gzip_file.write(tar_buffer.getvalue())
    return describe_artifact(kind, output_path)


def describe_artifact(kind: str, path: Path) -> BuiltArtifact:
    data = path.read_bytes()
    return BuiltArtifact(
        kind=kind,
        filename=path.name,
        path=path,
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
    )


def validate_codex_artifact(path: Path, version: str) -> Dict[str, Any]:
    prefix = f"roadmap-delivery-codex-skill-{version}"
    required = {
        f"{prefix}/SKILL.md",
        f"{prefix}/references/phase-loop.md",
        f"{prefix}/scripts/validate_delivery_artifacts.py",
    }
    with tarfile.open(path, "r:gz") as archive:
        names = set(archive.getnames())
    missing = sorted(required - names)
    forbidden = [
        name
        for name in names
        if name.startswith("/")
        or ".." in PurePosixPath(name).parts
        or name.startswith(("automation/", "roadmaps/", ".git/"))
        or ".codex" in PurePosixPath(name).parts
    ]
    status = "passed" if not missing and not forbidden else "failed"
    return {
        "status": status,
        "required_entries_present": not missing,
        "missing": missing,
        "forbidden_entries": forbidden,
        "entries": len(names),
    }


def validate_claude_artifact(path: Path, version: str) -> Dict[str, Any]:
    prefix = f"roadmap-delivery-claude-plugin-{version}"
    required = {
        f"{prefix}/.claude-plugin/plugin.json",
        f"{prefix}/README.md",
        f"{prefix}/skills/roadmap-delivery-skill/SKILL.md",
        f"{prefix}/agents/reviewer.md",
        f"{prefix}/hooks/hooks.json",
        f"{prefix}/hooks/roadmap_delivery_safety.py",
    }
    with tarfile.open(path, "r:gz") as archive:
        names = set(archive.getnames())
        manifest_member = archive.extractfile(f"{prefix}/.claude-plugin/plugin.json")
        manifest = json.loads(manifest_member.read().decode("utf-8")) if manifest_member else {}
    missing = sorted(required - names)
    forbidden = [
        name
        for name in names
        if name.startswith("/")
        or ".." in PurePosixPath(name).parts
        or "/automation/" in name
        or "/roadmaps/" in name
        or "/.git/" in name
        or ".codex" in PurePosixPath(name).parts
        or name.endswith("/agents/openai.yaml")
    ]
    manifest_ok = manifest.get("name") == "roadmap-delivery" and manifest.get("version") == version
    status = "passed" if not missing and not forbidden and manifest_ok else "failed"
    return {
        "status": status,
        "required_entries_present": not missing,
        "manifest_identity_valid": manifest_ok,
        "missing": missing,
        "forbidden_entries": forbidden,
        "entries": len(names),
    }


def validate_generic_artifact(path: Path, version: str) -> Dict[str, Any]:
    prefix = f"roadmap-delivery-generic-markdown-pack-{version}"
    required = {
        f"{prefix}/README.md",
        f"{prefix}/cli/install.md",
        f"{prefix}/checklists/future-adapter.md",
        f"{prefix}/capabilities/generic.yaml",
        f"{prefix}/schemas/delivery_state.schema.json",
        f"{prefix}/workflow/phase-loop.md",
    }
    with tarfile.open(path, "r:gz") as archive:
        names = set(archive.getnames())
    missing = sorted(required - names)
    forbidden = [
        name
        for name in names
        if name.startswith("/")
        or ".." in PurePosixPath(name).parts
        or "/automation/" in name
        or "/roadmaps/" in name
        or "/.git/" in name
        or ".codex" in PurePosixPath(name).parts
    ]
    status = "passed" if not missing and not forbidden else "failed"
    return {
        "status": status,
        "required_entries_present": not missing,
        "missing": missing,
        "forbidden_entries": forbidden,
        "entries": len(names),
    }


def run_json_command(command: Sequence[str], *, cwd: Path) -> Dict[str, Any]:
    proc = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"stdout": proc.stdout.strip()}
    return {
        "command": list(command),
        "returncode": proc.returncode,
        "stdout": payload,
        "stderr": proc.stderr.strip(),
        "status": "passed" if proc.returncode == 0 else "failed",
    }


def write_json(path: Path, payload: Dict[str, Any]) -> BuiltArtifact:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    return describe_artifact("release_manifest", path)


def write_checksums(path: Path, artifacts: Sequence[BuiltArtifact]) -> BuiltArtifact:
    lines = [f"{artifact.sha256}  {artifact.filename}\n" for artifact in sorted(artifacts, key=lambda item: item.filename)]
    path.write_text("".join(lines), encoding="utf-8")
    return describe_artifact("checksums", path)


def artifact_report_by_kind(artifacts: Sequence[BuiltArtifact]) -> Dict[str, BuiltArtifact]:
    return {artifact.kind: artifact for artifact in artifacts}


def release_package_metadata(version: str, artifacts: Sequence[BuiltArtifact]) -> List[Dict[str, Any]]:
    by_kind = artifact_report_by_kind(artifacts)

    def package(
        *,
        name: str,
        host: str,
        kind: str,
        install_source: str,
        support_status: str,
        capabilities: Sequence[str],
        limitations: Sequence[str],
    ) -> Dict[str, Any]:
        artifact = by_kind[kind]
        return {
            "name": name,
            "host": host,
            "version": version,
            "artifact": artifact.filename,
            "sha256": artifact.sha256,
            "size": artifact.size,
            "install_source": install_source,
            "support_status": support_status,
            "capability_summary": list(capabilities),
            "limitations": list(limitations),
        }

    return [
        package(
            name="roadmap-delivery-codex-skill",
            host="codex",
            kind="codex_skill_package",
            install_source=CODEX_SKILL_ROOT,
            support_status="supported",
            capabilities=(
                "Generated Codex skill instruction package.",
                "File-backed inspection and validation helper scripts.",
                "Phase model policy and blocked-remediation workflow guidance.",
                "Same-context review fallback when subagent review is unavailable.",
            ),
            limitations=(
                "Installed-skill synchronization is human-approved.",
                "Live Codex binary checks are optional and environment-dependent.",
            ),
        ),
        package(
            name="roadmap-delivery-claude-plugin",
            host="claude",
            kind="claude_plugin_package",
            install_source=CLAUDE_PLUGIN_ROOT,
            support_status="supported_local_plugin_package",
            capabilities=(
                "Generated local Claude plugin package.",
                "Packaged roadmap delivery skill, reviewer agent, and safety hooks.",
                "File-backed CLI validation against the same repository artifacts.",
                "Host-specific recurring automation is not assumed.",
            ),
            limitations=(
                "Installed-plugin synchronization is human-approved.",
                "Live Claude binary checks are optional and environment-dependent.",
            ),
        ),
        package(
            name="roadmap-delivery-generic-markdown-pack",
            host="generic",
            kind="generic_markdown_pack",
            install_source="generated release artifact",
            support_status="documentation_template",
            capabilities=(
                "Documentation and schema pack for future host adapter planning.",
                "No runtime integration claim for named hosts.",
                "Approval-boundary and validation guidance for future adapters.",
            ),
            limitations=(
                "Not a supported runtime package.",
                "Future hosts need their own capability file, adapter package, tests, and smoke checks.",
            ),
        ),
    ]


def build_once(repo_root: Path, output_dir: Path, *, include_paths: bool) -> Dict[str, Any]:
    version = read_version(repo_root)
    validate_release_inputs(repo_root, version)
    output_dir.mkdir(parents=True, exist_ok=True)

    adapter_check = run_json_command(
        [sys.executable, "scripts/build_adapters.py", "--check", "--json"],
        cwd=repo_root,
    )
    if adapter_check["returncode"] != 0:
        raise ReleaseBuildError("Codex and Claude adapter generation check failed")

    codex_check = run_json_command(
        [sys.executable, "scripts/build_codex_package.py", "--check", "--json"],
        cwd=repo_root,
    )
    if codex_check["returncode"] != 0:
        raise ReleaseBuildError("Codex package generation check failed")

    primary_artifacts = [
        write_tar_gz(repo_root, output_dir / spec.filename, spec)
        for spec in artifact_specs(version)
    ]
    with tempfile.TemporaryDirectory(prefix="roadmap-delivery-generic-pack-") as generic_dir:
        generic_root = Path(generic_dir)
        generic_build = run_json_command(
            [
                sys.executable,
                "scripts/build_adapters.py",
                "--adapter",
                "generic",
                "--write",
                "--output-root",
                str(generic_root),
                "--json",
            ],
            cwd=repo_root,
        )
        if generic_build["returncode"] != 0:
            raise ReleaseBuildError("Generic markdown pack generation failed")
        primary_artifacts.append(
            write_directory_tar_gz(
                generic_root / "generic",
                output_dir / generic_artifact_filename(version),
                kind="generic_markdown_pack",
                prefix=f"roadmap-delivery-generic-markdown-pack-{version}",
            )
        )
    codex_artifact = next(item for item in primary_artifacts if item.kind == "codex_skill_package")
    codex_artifact_validation = validate_codex_artifact(codex_artifact.path, version)
    if codex_artifact_validation["status"] != "passed":
        raise ReleaseBuildError("Codex package artifact validation failed")
    claude_artifact = next(item for item in primary_artifacts if item.kind == "claude_plugin_package")
    claude_artifact_validation = validate_claude_artifact(claude_artifact.path, version)
    if claude_artifact_validation["status"] != "passed":
        raise ReleaseBuildError("Claude plugin artifact validation failed")
    generic_artifact = next(item for item in primary_artifacts if item.kind == "generic_markdown_pack")
    generic_artifact_validation = validate_generic_artifact(generic_artifact.path, version)
    if generic_artifact_validation["status"] != "passed":
        raise ReleaseBuildError("Generic markdown artifact validation failed")

    manifest_payload = {
        "schema_version": 1,
        "name": "roadmap-delivery",
        "version": version,
        "version_policy": "VERSION is the repository release version; external publication is human-approved.",
        "release_notes": {
            "path": release_notes_path(version),
            "source_of_truth_for": [
                "first-release contents",
                "known limitations",
                "local verification commands",
                "publication boundary",
            ],
        },
        "artifacts": [artifact.as_report(include_path=False) for artifact in primary_artifacts],
        "packages": release_package_metadata(version, primary_artifacts),
        "verification_commands": list(RELEASE_VERIFICATION_COMMANDS),
        "compatibility": {
            "codex_skill_path": CODEX_SKILL_ROOT,
            "claude_plugin_path": CLAUDE_PLUGIN_ROOT,
            "generic_markdown_pack": "documentation-only adapter preparation pack",
            "helper_scripts_remain_wrappers": True,
            "legacy_state_compatibility": "warning-backed where validators allow it",
            "supported_host_packages": ["codex", "claude"],
        },
        "publication": {
            "external_publication": False,
            "requires_human_approval": True,
        },
    }
    manifest = write_json(output_dir / f"roadmap-delivery-{version}-manifest.json", manifest_payload)
    checksums = write_checksums(output_dir / f"roadmap-delivery-{version}-checksums.sha256", [*primary_artifacts, manifest])
    all_artifacts = [*primary_artifacts, manifest, checksums]

    privacy_scan = run_json_command(
        [
            sys.executable,
            "scripts/check_release_privacy.py",
            "--repo-root",
            str(repo_root),
            "--json",
            *[part for artifact in primary_artifacts for part in ("--bundle", str(artifact.path))],
        ],
        cwd=repo_root,
    )
    if privacy_scan["returncode"] != 0:
        raise ReleaseBuildError("Release privacy scan failed")

    return {
        "schema_version": 1,
        "status": "ok",
        "version": version,
        "output_dir": str(output_dir) if include_paths else None,
        "artifacts": [artifact.as_report(include_path=include_paths) for artifact in all_artifacts],
        "adapter_check": {
            "status": adapter_check["status"],
            "package_status": adapter_check["stdout"].get("status") if isinstance(adapter_check["stdout"], dict) else None,
        },
        "codex_package_check": {
            "status": codex_check["status"],
            "package_status": codex_check["stdout"].get("status") if isinstance(codex_check["stdout"], dict) else None,
        },
        "codex_artifact_validation": codex_artifact_validation,
        "claude_artifact_validation": claude_artifact_validation,
        "generic_artifact_validation": generic_artifact_validation,
        "privacy_scan": {
            "status": privacy_scan["status"],
            "scanner_status": privacy_scan["stdout"].get("status") if isinstance(privacy_scan["stdout"], dict) else None,
            "findings": len(privacy_scan["stdout"].get("findings", [])) if isinstance(privacy_scan["stdout"], dict) else None,
        },
        "errors": [],
    }


def artifact_fingerprint(report: Dict[str, Any]) -> Dict[str, str]:
    return {
        str(artifact["filename"]): str(artifact["sha256"])
        for artifact in report.get("artifacts", [])
    }


def run_check(repo_root: Path) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="roadmap-delivery-release-a-") as first_dir:
        first = build_once(repo_root, Path(first_dir), include_paths=False)
        with tempfile.TemporaryDirectory(prefix="roadmap-delivery-release-b-") as second_dir:
            second = build_once(repo_root, Path(second_dir), include_paths=False)
    reproducible = artifact_fingerprint(first) == artifact_fingerprint(second)
    first["check"] = True
    first["reproducible"] = reproducible
    if not reproducible:
        first["status"] = "failed"
        first["errors"] = ["Release artifacts are not reproducible across two builds."]
    return first


def print_text(report: Dict[str, Any]) -> None:
    print(f"status: {report['status']}")
    print(f"version: {report.get('version')}")
    print(f"check: {report.get('check', False)}")
    print(f"reproducible: {report.get('reproducible', True)}")
    print(f"output_dir: {report.get('output_dir')}")
    print("artifacts:")
    for artifact in report.get("artifacts", []):
        print(f"- {artifact['filename']} {artifact['sha256']} ({artifact['size']} bytes)")
    print(f"errors: {len(report.get('errors', []))}")
    for error in report.get("errors", []):
        print(f"- {error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--output-dir", default="dist", help="Output directory for release artifacts.")
    parser.add_argument("--check", action="store_true", help="Build twice in temporary directories and verify reproducibility.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()

    try:
        if args.check:
            report = run_check(repo_root)
        else:
            output_dir = Path(args.output_dir)
            if not output_dir.is_absolute():
                output_dir = repo_root / output_dir
            report = build_once(repo_root, output_dir.resolve(), include_paths=True)
            report["check"] = False
            report["reproducible"] = True
    except (OSError, ReleaseBuildError, tarfile.TarError) as exc:
        report = {
            "schema_version": 1,
            "status": "failed",
            "version": None,
            "output_dir": None,
            "artifacts": [],
            "check": bool(args.check),
            "reproducible": False,
            "errors": [str(exc)],
        }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
