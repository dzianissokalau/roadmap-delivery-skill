#!/usr/bin/env python3
"""Compatibility wrapper for roadmap_delivery.validation."""

from __future__ import annotations

from pathlib import Path
import sys


# Load the packaged runtime first. Repository fallback is development-only.
_script_root = Path(__file__).resolve().parents[1]
_runtime = _script_root / "runtime"
if _runtime.is_dir():
    sys.path.insert(0, str(_runtime))
elif (_script_root.name == "templates" and _script_root.parent.name == "codex"
      and _script_root.parent.parent.name == "adapters"
      and (_script_root.parents[2] / "pyproject.toml").is_file()):
    sys.path.insert(0, str(_script_root.parents[2] / "src"))
elif (_script_root / "SKILL.md").is_file():
    print("roadmap-delivery runtime missing; reinstall the complete package.", file=sys.stderr)
    raise SystemExit(2)
else:
    for _parent in Path(__file__).resolve().parents:
        if (_parent / "pyproject.toml").is_file() and (_parent / "src/roadmap_delivery").is_dir():
            sys.path.insert(0, str(_parent / "src"))
            break
try:
    from roadmap_delivery.paths import runtime_resource_root
    runtime_resource_root()
except (ImportError, ValueError) as _exc:
    print("roadmap-delivery runtime unavailable: " + str(_exc), file=sys.stderr)
    raise SystemExit(2) from _exc


try:
    from roadmap_delivery.validation import main
except ModuleNotFoundError as exc:
    if exc.name == "roadmap_delivery":
        print(
            "roadmap_delivery package is not importable. Run this script from "
            "the repository checkout or install the roadmap-delivery package.",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    raise


if __name__ == "__main__":
    raise SystemExit(main())
