"""TOML parsing and value-preserving serialization for runner configuration.

Execution requires a real parser. Python 3.11+ supplies tomllib; older hosts
may supply tomli (or pip's bundled tomli during the repository migration).
No permissive line parser is used for either inspection or mutation.
"""

from __future__ import annotations

from datetime import date, datetime, time
import importlib
import json
import math
from pathlib import Path
from typing import Any, Dict


class TomlError(ValueError):
    """Invalid TOML or an unavailable parser; never an execution fallback."""


def parse_toml(text: str) -> Dict[str, Any]:
    parser = None
    for name in ("tomllib", "tomli", "pip._vendor.tomli"):
        try:
            parser = importlib.import_module(name)
            break
        except ImportError:
            continue
    if parser is None:
        raise TomlError("Real TOML parser unavailable; use Python 3.11+ or provide tomli.")
    try:
        return parser.loads(text)
    except ValueError as exc:
        raise TomlError(f"Invalid TOML: {exc}") from exc


def parse_minimal_toml(path: Path) -> Dict[str, Any]:
    """Compatibility name; now parses the complete TOML document strictly."""
    return parse_toml(path.read_text(encoding="utf-8"))


def _value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(json.dumps(key) + " = " + _value(item) for key, item in value.items()) + " }"
    raise TomlError(f"Unsupported TOML value type: {type(value).__name__}")


def dump_toml(data: Dict[str, Any]) -> str:
    """Preserve values, including nested tables; formatting is normalized."""
    text = "".join(json.dumps(key) + " = " + _value(value) + "\n" for key, value in data.items())
    parsed = parse_toml(text)
    if parsed != data:
        raise TomlError("Serialized candidate does not preserve TOML values.")
    return text
