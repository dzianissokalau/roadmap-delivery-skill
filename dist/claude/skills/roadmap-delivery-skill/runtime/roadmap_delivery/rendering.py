"""Deterministic host adapter package rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import stat
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


class AdapterRenderError(RuntimeError):
    """Raised when an adapter package cannot be rendered safely."""


@dataclass(frozen=True)
class FileSpec:
    """One generated package file."""

    output: str
    template: Optional[str] = None
    source: Optional[str] = None
    literal: Optional[str] = None
    mode: Optional[int] = None
    core_source: Optional[str] = None


@dataclass(frozen=True)
class AdapterMetadata:
    """Host adapter rendering metadata."""

    adapter: str
    output_dir: str
    files: Sequence[FileSpec]
    template_dir: Optional[str] = None
    capability_file: Optional[str] = None
    output_committed: bool = True


@dataclass(frozen=True)
class RenderedFile:
    """A file rendered from adapter metadata."""

    output: str
    content: bytes
    template: Optional[str] = None
    source: Optional[str] = None
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


@dataclass(frozen=True)
class RenderedPackage:
    """Rendered adapter package plus the output directory it targets."""

    metadata: AdapterMetadata
    output_dir: Path
    files: Sequence[RenderedFile]
    capability_content: Optional[bytes] = None

    @property
    def capability_sha256(self) -> Optional[str]:
        if self.capability_content is None:
            return None
        return hashlib.sha256(self.capability_content).hexdigest()


def safe_relative_path(value: Any, *, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise AdapterRenderError(f"{field} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise AdapterRenderError(f"{field} must stay inside the repository: {value!r}")
    return path


def parse_mode(value: Any, *, output: str) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        mode = value
    elif isinstance(value, str) and value.startswith("0"):
        try:
            mode = int(value, 8)
        except ValueError as exc:
            raise AdapterRenderError(f"mode for {output} is not valid octal: {value!r}") from exc
    else:
        raise AdapterRenderError(f"mode for {output} must be an octal string")
    if mode < 0 or mode > 0o777:
        raise AdapterRenderError(f"mode for {output} is outside file permission range")
    return mode


def read_manifest_metadata(
    repo_root: Path,
    manifest_path: Path,
    *,
    adapter: str,
    capability_file: Optional[str],
    output_committed: bool,
) -> AdapterMetadata:
    path = manifest_path if manifest_path.is_absolute() else repo_root / manifest_path
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AdapterRenderError(f"Manifest is invalid JSON: {path}: {exc}") from exc
    except OSError as exc:
        raise AdapterRenderError(f"Cannot read manifest: {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise AdapterRenderError(f"Manifest root is not an object: {path}")
    if manifest.get("schema_version") != 1:
        raise AdapterRenderError("Manifest schema_version must be 1")
    if manifest.get("adapter") != adapter:
        raise AdapterRenderError(f"Manifest adapter must be {adapter!r}")
    if not isinstance(manifest.get("files"), list) or not manifest["files"]:
        raise AdapterRenderError("Manifest files must be a non-empty array")

    files: List[FileSpec] = []
    for raw_entry in manifest["files"]:
        if not isinstance(raw_entry, dict):
            raise AdapterRenderError("Manifest file entries must be objects")
        output = safe_relative_path(raw_entry.get("output"), field="output").as_posix()
        template = safe_relative_path(raw_entry.get("template"), field="template").as_posix()
        core_source = raw_entry.get("core_source")
        if core_source is not None:
            core_source = safe_relative_path(core_source, field="core_source").as_posix()
        files.append(
            FileSpec(
                output=output,
                template=template,
                mode=parse_mode(raw_entry.get("mode"), output=output),
                core_source=core_source if isinstance(core_source, str) else None,
            )
        )

    return AdapterMetadata(
        adapter=adapter,
        output_dir=safe_relative_path(manifest.get("output_dir"), field="output_dir").as_posix(),
        template_dir=safe_relative_path(manifest.get("template_dir"), field="template_dir").as_posix(),
        capability_file=capability_file,
        output_committed=output_committed,
        files=files,
    )


def render_package(
    repo_root: Path,
    metadata: AdapterMetadata,
    *,
    output_dir: Optional[Path] = None,
) -> RenderedPackage:
    if not metadata.files:
        raise AdapterRenderError(f"{metadata.adapter} adapter metadata must define at least one file")
    rendered: List[RenderedFile] = []
    seen_outputs = set()
    template_dir = repo_root / safe_relative_path(metadata.template_dir, field="template_dir") if metadata.template_dir else None
    package_output_dir = output_dir or repo_root / safe_relative_path(metadata.output_dir, field="output_dir")
    capability_content = _read_capability(repo_root, metadata.capability_file)

    for spec in metadata.files:
        output = safe_relative_path(spec.output, field="output").as_posix()
        if output in seen_outputs:
            raise AdapterRenderError(f"Duplicate output path in adapter metadata: {output}")
        seen_outputs.add(output)
        content, template, source = _read_spec_content(repo_root, template_dir, spec)
        core_content = _read_core_source(repo_root, spec.core_source, output=output)
        rendered.append(
            RenderedFile(
                output=output,
                template=template,
                source=source,
                content=content,
                mode=spec.mode,
                core_source=spec.core_source,
                core_content=core_content,
            )
        )

    return RenderedPackage(
        metadata=metadata,
        output_dir=package_output_dir,
        files=rendered,
        capability_content=capability_content,
    )


def _read_capability(repo_root: Path, capability_file: Optional[str]) -> Optional[bytes]:
    if capability_file is None:
        return None
    path = repo_root / safe_relative_path(capability_file, field="capability_file")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AdapterRenderError(f"Cannot read host capability file {path}: {exc}") from exc


def _read_spec_content(
    repo_root: Path,
    template_dir: Optional[Path],
    spec: FileSpec,
) -> Tuple[bytes, Optional[str], Optional[str]]:
    kinds = [spec.template is not None, spec.source is not None, spec.literal is not None]
    if sum(1 for item in kinds if item) != 1:
        raise AdapterRenderError(f"{spec.output} must define exactly one of template, source, or literal")
    if spec.template is not None:
        if template_dir is None:
            raise AdapterRenderError(f"{spec.output} uses a template but no template_dir is configured")
        template = safe_relative_path(spec.template, field="template").as_posix()
        path = template_dir / template
        try:
            return path.read_bytes(), template, None
        except OSError as exc:
            raise AdapterRenderError(f"Cannot read template {path}: {exc}") from exc
    if spec.source is not None:
        source = safe_relative_path(spec.source, field="source").as_posix()
        path = repo_root / source
        try:
            return path.read_bytes(), None, source
        except OSError as exc:
            raise AdapterRenderError(f"Cannot read source {path}: {exc}") from exc
    return str(spec.literal).encode("utf-8"), None, None


def _read_core_source(repo_root: Path, core_source: Optional[str], *, output: str) -> Optional[bytes]:
    if core_source is None:
        return None
    core_path = repo_root / safe_relative_path(core_source, field="core_source")
    if not core_path.exists():
        raise AdapterRenderError(f"Missing canonical core source for {output}: {core_path}")
    try:
        return core_path.read_bytes()
    except OSError as exc:
        raise AdapterRenderError(f"Cannot read canonical core source for {output}: {core_path}: {exc}") from exc


def iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file()
                  and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo"))


def file_mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def compare_output(output_dir: Path, rendered: Sequence[RenderedFile]) -> List[Dict[str, str]]:
    diffs: List[Dict[str, str]] = []
    expected = {item.output: item for item in rendered}

    for item in rendered:
        target = output_dir / item.output
        if not target.exists():
            diffs.append({"path": item.output, "kind": "missing", "message": "Rendered file is missing from package output."})
            continue
        actual = target.read_bytes()
        if actual != item.content:
            diffs.append({"path": item.output, "kind": "content", "message": "Package output differs from adapter render."})
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
            diffs.append({"path": rel, "kind": "unexpected", "message": "Package output file is not generated by adapter metadata."})

    return diffs


def write_output(output_dir: Path, rendered: Sequence[RenderedFile]) -> None:
    for item in rendered:
        target = output_dir / item.output
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.content)
        if item.mode is not None:
            target.chmod(item.mode)


def rendered_file_report(rendered: Sequence[RenderedFile]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in rendered:
        row: Dict[str, Any] = {
            "path": item.output,
            "sha256": item.sha256,
            "size": len(item.content),
        }
        if item.template is not None:
            row["template"] = item.template
        if item.source is not None:
            row["source"] = item.source
        if item.mode_text is not None:
            row["mode"] = item.mode_text
        if item.core_source:
            row["core_source"] = item.core_source
            row["core_sha256"] = item.core_sha256
            row["core_size"] = len(item.core_content or b"")
        rows.append(row)
    return rows


def build_adapter_report(
    package: RenderedPackage,
    *,
    diffs: Sequence[Dict[str, str]],
    errors: Sequence[str],
    wrote: bool,
    checked_output: bool,
) -> Dict[str, Any]:
    status = "error" if errors else "drift" if diffs else "ok"
    report: Dict[str, Any] = {
        "schema_version": 1,
        "adapter": package.metadata.adapter,
        "status": status,
        "output_dir": str(package.output_dir),
        "output_committed": package.metadata.output_committed,
        "check_mode": "output" if checked_output else "render_only",
        "wrote": wrote,
        "file_count": len(package.files),
        "files": rendered_file_report(package.files),
        "diffs": list(diffs),
        "errors": list(errors),
    }
    if package.metadata.capability_file is not None:
        report["capability_file"] = package.metadata.capability_file
        report["capability_sha256"] = package.capability_sha256
        report["capability_size"] = len(package.capability_content or b"")
    return report


def aggregate_status(reports: Sequence[Dict[str, Any]]) -> str:
    if any(report.get("status") == "error" for report in reports):
        return "error"
    if any(report.get("status") == "drift" for report in reports):
        return "drift"
    return "ok"


def portable_runtime_files(repo_root: Path, prefix: str = "runtime") -> List[RenderedFile]:
    """Explicit dependency closure: stdlib-only modules and canonical schema data."""
    root = repo_root / "src" / "roadmap_delivery"
    payload = {"roadmap_delivery/" + path.name: path.read_bytes() for path in sorted(root.glob("*.py"))}
    payload["VERSION"] = (repo_root / "VERSION").read_bytes()
    payload["roadmap_delivery/_resources/VERSION"] = payload["VERSION"]
    for path in sorted((repo_root / "schemas").glob("*.json")):
        payload["roadmap_delivery/_resources/schemas/" + path.name] = path.read_bytes()
    manifest = {"schema_version": 1, "version": payload["VERSION"].decode().strip(),
                "python": ">=3.12,<3.13", "dependencies": "Python standard library only",
                "files": {name.removeprefix("roadmap_delivery/"): hashlib.sha256(data).hexdigest()
                          for name, data in payload.items() if name.startswith("roadmap_delivery/")}}
    payload["roadmap_delivery/_resources/runtime-manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    return [RenderedFile(output=prefix + "/" + name, content=data, mode=0o644) for name, data in sorted(payload.items())]
