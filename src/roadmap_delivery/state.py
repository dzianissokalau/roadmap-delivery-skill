"""State file loading helpers."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
import tempfile
from typing import Any, Dict
import stat


class JsonObjectError(RuntimeError):
    """Raised when a JSON file cannot be read as an object."""


def review_verdict(text: str) -> str | None:
    """Read one explicit verdict, excluding fenced examples and quoted prose."""
    lines = []
    fence = None
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is None:
            lines.append(line)
    body = "\n".join(lines)
    verdicts = re.findall(r"(?im)^Verdict:[ \t]*([A-Za-z_-]+)[ \t]*$", body)
    verdicts += re.findall(r"(?im)^##[ \t]+Verdict[ \t]*\n\s*([A-Za-z_-]+)[ \t]*(?:\n|$)", body)
    if len(verdicts) != 1:
        return None
    verdict = verdicts[0].lower()
    return verdict if verdict in {"delivered", "needs-fix", "blocked"} else None


def load_json_object(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            value = json.load(fh)
    except json.JSONDecodeError as exc:
        raise JsonObjectError(f"Invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise JsonObjectError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise JsonObjectError(f"JSON root is not an object: {path}")
    return value


def atomic_write_text(path: Path, text: str) -> None:
    """Replace a complete fsynced file, preserving existing permissions."""
    temporary = None
    try:
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="." + path.name, delete=False) as fh:
            temporary = Path(fh.name)
            fh.write(text)
            fh.flush()
            os.fchmod(fh.fileno(), mode)
            os.fsync(fh.fileno())
        os.replace(str(temporary), str(path))
        directory = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as exc:
        raise JsonObjectError(f"Cannot write {path}: {exc}") from exc
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def write_json_object(path: Path, value: Dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, sort_keys=False) + "\n")
