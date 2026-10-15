"""Shared roadmap delivery framework helpers."""

from __future__ import annotations

from importlib import metadata as importlib_metadata
from pathlib import Path


__all__ = ["__version__"]


def _read_version() -> str:
    package = Path(__file__).resolve().parent
    root = package.parent.parent
    # Only the canonical source layout may use a checkout VERSION. Installed
    # packages must not inherit a target project's unrelated version file.
    if package.parent.name == "src" and (root / "pyproject.toml").is_file() and (root / "adapters").is_dir():
        return (root / "VERSION").read_text(encoding="utf-8").strip()
    version_path = package / "_resources/VERSION"
    if version_path.is_file():
        return version_path.read_text(encoding="utf-8").strip()
    try:
        return importlib_metadata.version("roadmap-delivery")
    except importlib_metadata.PackageNotFoundError:
        pass
    return "0.0.0"


__version__ = _read_version()
