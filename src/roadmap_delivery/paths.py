"""Path and slug helpers shared by roadmap delivery tools."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Dict, Iterable, List, Optional, TypeVar


T = TypeVar("T")


def unique(items: Iterable[T]) -> List[T]:
    seen = set()
    out: List[T] = []
    for item in items:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def unique_paths(paths: Iterable[Path]) -> List[Path]:
    seen = set()
    out: List[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen:
            out.append(path)
            seen.add(key)
    return out


def slug_forms(slug: Optional[str]) -> Dict[str, Optional[str]]:
    if not slug:
        return {"input": None, "dash": None, "dir": None}
    return {
        "input": slug,
        "dash": slug.replace("_", "-"),
        "dir": slug.replace("-", "_"),
    }


def resolve_repo_path(repo_root: Path, value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return repo_root / path


def path_for_report(path: Optional[Path]) -> Optional[str]:
    return str(path) if path is not None else None


def state_candidates(repo_root: Path, forms: Dict[str, Optional[str]]) -> List[Path]:
    candidates: List[Path] = []
    for slug in unique([item for item in (forms.get("dir"), forms.get("dash")) if item]):
        candidates.append(repo_root / "roadmaps" / "automation" / slug / "delivery_state.json")
        candidates.append(repo_root / "automation" / slug / "delivery_state.json")
    return unique_paths(candidates)


def automation_dir_candidates(repo_root: Path, forms: Dict[str, Optional[str]]) -> List[Path]:
    candidates: List[Path] = []
    for slug in unique([item for item in (forms.get("dir"), forms.get("dash")) if item]):
        candidates.append(repo_root / "roadmaps" / "automation" / slug)
        candidates.append(repo_root / "automation" / slug)
    return unique_paths(candidates)


def extract_roadmap_references(
    prompt: str,
    repo_root: Path,
    *,
    require_roadmap_suffix: bool = False,
) -> List[Path]:
    refs: List[Path] = []
    patterns = (
        r"/Users/[^`'\"\s]+?\.md",
        r"roadmaps/[^`'\"\s]+?\.md",
    )
    for pattern in patterns:
        for match in re.findall(pattern, prompt):
            path = Path(match)
            if require_roadmap_suffix:
                if not (path.name == "roadmap.md" or path.name.endswith("_roadmap.md")):
                    continue
            elif "roadmap" not in path.name:
                continue
            if not path.is_absolute():
                path = repo_root / path
            if path not in refs:
                refs.append(path)
    return refs


def lifecycle_roadmap_stem(path: Path) -> Optional[str]:
    """Return a roadmap filename stem without lifecycle prefix."""

    name = path.name
    if not name.endswith(".md"):
        return None
    stem = name[:-3]
    for prefix in ("not_started_", "in_progress_", "delivered_"):
        if stem.startswith(prefix):
            return stem[len(prefix) :]
    return stem


def is_lifecycle_roadmap_sibling(candidate: Path, current: Path) -> bool:
    """Return true when two paths name the same roadmap lifecycle."""

    candidate_stem = lifecycle_roadmap_stem(candidate)
    current_stem = lifecycle_roadmap_stem(current)
    if not candidate_stem or not current_stem:
        return False
    return candidate_stem == current_stem


def package_repo_root(start: Optional[Path] = None) -> Optional[Path]:
    """Recognize the development layout only; never search arbitrary ancestors."""
    package = (start or Path(__file__)).resolve().parent
    root = package.parent.parent
    if package.parent.name == "src" and (root / "pyproject.toml").is_file() and (root / "adapters").is_dir():
        return root
    return None


def runtime_resource_root() -> Path:
    """Resolve and verify installed resources; missing/mixed bundles fail closed."""
    import hashlib
    import json
    import sys
    from . import __version__

    development = package_repo_root()
    if development is not None:
        return development
    if sys.version_info[:2] != (3, 12):
        raise ValueError("Portable roadmap-delivery requires Python 3.12; select a Python 3.12 interpreter.")
    package = Path(__file__).resolve().parent
    resources = package / "_resources"
    try:
        manifest = json.loads((resources / "runtime-manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Invalid runtime/resource manifest; reinstall the complete package.")
        if manifest.get("schema_version") != 1 or manifest.get("version") != __version__:
            raise ValueError("Mixed runtime/resource versions; reinstall the complete package.")
        expected = manifest["files"]
        required = {"_resources/VERSION", "__init__.py", "paths.py"}
        required.update("_resources/schemas/" + name for name in (
            "delivery_state.schema.json", "phase_model_policy.schema.json",
            "review_artifact.schema.json", "automation_run_log.schema.json"))
        if not isinstance(expected, dict) or not required.issubset(expected):
            raise ValueError("Incomplete runtime/resource manifest; reinstall the complete package.")
        for name, digest in expected.items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe runtime manifest path.")
            target = package / relative
            if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError("Mixed or damaged runtime/resources: " + name + "; reinstall the complete package.")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Incomplete runtime/resources; reinstall the complete package: " + str(exc)) from exc
    return resources


# Every installed command imports paths, including the separate CLI and planners.
# Check before any command can mutate a target project or host fixture.
if package_repo_root() is None:
    runtime_resource_root()
