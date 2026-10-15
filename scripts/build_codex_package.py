#!/usr/bin/env python3
"""Render or check the committed Codex roadmap-delivery skill package."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import stat
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_MANIFEST = Path("adapters/codex/package_manifest.json")


class PackageBuildError(RuntimeError):
    """Raised when the adapter package cannot be rendered safely."""


@dataclass(frozen=True)
class RenderedFile:
    output: str
    template: str
    content: bytes
    mode: Optional[int] = None
    core_source: Optional[str] = None
    core_content: Optional[bytes] = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    @property
    def mode_text(self) -> Optional[str]:
        if self.mode is None:
            return None
        return f"{self.mode:04o}"

    @property
    def core_sha256(self) -> Optional[str]:
        if self.core_content is None:
            return None
        return hashlib.sha256(self.core_content).hexdigest()


def safe_relative_path(value: Any, *, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise PackageBuildError(f"{field} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise PackageBuildError(f"{field} must stay inside the repository: {value!r}")
    return path


def load_manifest(repo_root: Path, manifest_path: Path) -> Dict[str, Any]:
    path = manifest_path
    if not path.is_absolute():
        path = repo_root / path
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PackageBuildError(f"Manifest is invalid JSON: {path}: {exc}") from exc
    except OSError as exc:
        raise PackageBuildError(f"Cannot read manifest: {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise PackageBuildError(f"Manifest root is not an object: {path}")
    if manifest.get("schema_version") != 1:
        raise PackageBuildError("Manifest schema_version must be 1")
    if manifest.get("adapter") != "codex":
        raise PackageBuildError("Manifest adapter must be 'codex'")
    if not isinstance(manifest.get("files"), list) or not manifest["files"]:
        raise PackageBuildError("Manifest files must be a non-empty array")
    return manifest


def parse_mode(value: Any, *, output: str) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.startswith("0"):
        raise PackageBuildError(f"mode for {output} must be an octal string")
    try:
        mode = int(value, 8)
    except ValueError as exc:
        raise PackageBuildError(f"mode for {output} is not valid octal: {value!r}") from exc
    if mode < 0 or mode > 0o777:
        raise PackageBuildError(f"mode for {output} is outside file permission range")
    return mode


def render_package(repo_root: Path, manifest: Dict[str, Any]) -> Tuple[List[RenderedFile], Path]:
    template_dir = repo_root / safe_relative_path(manifest.get("template_dir"), field="template_dir")
    output_dir = repo_root / safe_relative_path(manifest.get("output_dir"), field="output_dir")
    rendered: List[RenderedFile] = []
    seen_outputs = set()

    for raw_entry in manifest["files"]:
        if not isinstance(raw_entry, dict):
            raise PackageBuildError("Manifest file entries must be objects")
        output_path = safe_relative_path(raw_entry.get("output"), field="output")
        template_path = safe_relative_path(raw_entry.get("template"), field="template")
        output = output_path.as_posix()
        template = template_path.as_posix()
        if output in seen_outputs:
            raise PackageBuildError(f"Duplicate output path in manifest: {output}")
        seen_outputs.add(output)

        source_path = template_dir / template_path
        try:
            content = source_path.read_bytes()
        except OSError as exc:
            raise PackageBuildError(f"Cannot read template {source_path}: {exc}") from exc

        core_source = raw_entry.get("core_source")
        core_content = None
        if core_source is not None:
            core_path = repo_root / safe_relative_path(core_source, field="core_source")
            if not core_path.exists():
                raise PackageBuildError(f"Missing canonical core source for {output}: {core_path}")
            try:
                core_content = core_path.read_bytes()
            except OSError as exc:
                raise PackageBuildError(f"Cannot read canonical core source for {output}: {core_path}: {exc}") from exc

        rendered.append(
            RenderedFile(
                output=output,
                template=template,
                content=content,
                mode=parse_mode(raw_entry.get("mode"), output=output),
                core_source=core_source if isinstance(core_source, str) else None,
                core_content=core_content,
            )
        )

    source = repo_root / "src"
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    from roadmap_delivery.rendering import portable_runtime_files
    rendered.extend(RenderedFile(output=item.output, template="<shared-runtime>", content=item.content, mode=item.mode)
                    for item in portable_runtime_files(repo_root))
    return rendered, output_dir


def iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file()
                  and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo"))


def file_mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def compare_output(output_dir: Path, rendered: List[RenderedFile]) -> List[Dict[str, str]]:
    diffs: List[Dict[str, str]] = []
    expected = {item.output: item for item in rendered}

    for item in rendered:
        target = output_dir / item.output
        if not target.exists():
            diffs.append({"path": item.output, "kind": "missing", "message": "Rendered file is missing from package output."})
            continue
        actual = target.read_bytes()
        if actual != item.content:
            diffs.append({"path": item.output, "kind": "content", "message": "Package output differs from adapter template render."})
        if item.mode is not None and file_mode(target) != item.mode:
            diffs.append(
                {
                    "path": item.output,
                    "kind": "mode",
                    "message": f"Package output mode is {file_mode(target):04o}, expected {item.mode:04o}.",
                }
            )

    for path in iter_files(output_dir):
        rel = path.relative_to(output_dir).as_posix()
        if rel not in expected:
            diffs.append({"path": rel, "kind": "unexpected", "message": "Package output file is not generated by the manifest."})

    return diffs


def write_output(output_dir: Path, rendered: List[RenderedFile]) -> None:
    for item in rendered:
        target = output_dir / item.output
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.content)
        if item.mode is not None:
            target.chmod(item.mode)


def rendered_file_report(rendered: List[RenderedFile]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in rendered:
        row: Dict[str, Any] = {
            "path": item.output,
            "template": item.template,
            "sha256": item.sha256,
            "size": len(item.content),
        }
        if item.mode_text is not None:
            row["mode"] = item.mode_text
        if item.core_source:
            row["core_source"] = item.core_source
            row["core_sha256"] = item.core_sha256
            row["core_size"] = len(item.core_content or b"")
        rows.append(row)
    return rows


def build_report(
    *,
    repo_root: Path,
    output_dir: Optional[Path],
    rendered: List[RenderedFile],
    diffs: List[Dict[str, str]],
    errors: List[str],
    wrote: bool,
) -> Dict[str, Any]:
    status = "error" if errors else "drift" if diffs else "ok"
    return {
        "schema_version": 1,
        "adapter": "codex",
        "status": status,
        "repo_root": str(repo_root),
        "output_dir": str(output_dir) if output_dir is not None else None,
        "wrote": wrote,
        "file_count": len(rendered),
        "files": rendered_file_report(rendered),
        "diffs": diffs,
        "errors": errors,
    }


def print_text(report: Dict[str, Any]) -> None:
    print(f"status: {report['status']}")
    print(f"adapter: {report['adapter']}")
    print(f"output_dir: {report['output_dir']}")
    print(f"files: {report['file_count']}")
    print(f"diffs: {len(report['diffs'])}")
    for diff in report["diffs"]:
        print(f"- {diff['kind']}: {diff['path']}: {diff['message']}")
    print(f"errors: {len(report['errors'])}")
    for error in report["errors"]:
        print(f"- {error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Adapter package manifest path.")
    parser.add_argument("--check", action="store_true", help="Check rendered output against the committed package.")
    parser.add_argument("--write", action="store_true", help="Write rendered output to the committed package directory.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.check and args.write:
        parser.error("--check and --write cannot be used together")

    repo_root = Path(args.repo_root).expanduser().resolve()
    errors: List[str] = []
    rendered: List[RenderedFile] = []
    output_dir: Optional[Path] = None
    diffs: List[Dict[str, str]] = []
    wrote = False

    try:
        manifest = load_manifest(repo_root, Path(args.manifest))
        rendered, output_dir = render_package(repo_root, manifest)
        if args.write:
            write_output(output_dir, rendered)
            wrote = True
        diffs = compare_output(output_dir, rendered)
    except PackageBuildError as exc:
        errors.append(str(exc))
    except OSError as exc:
        errors.append(str(exc))

    report = build_report(
        repo_root=repo_root,
        output_dir=output_dir,
        rendered=rendered,
        diffs=diffs,
        errors=errors,
        wrote=wrote,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)

    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
