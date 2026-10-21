"""Minimal JSON-Schema validator for tool-call arguments.

Covers the subset of JSON Schema that coding-agent tool definitions actually
use (type, properties, required, enum, items, additionalProperties,
minimum/maximum, minItems). Stdlib-only so comparators stay dependency-free.
Returns a list of human-readable problems; empty list means valid.
"""

from __future__ import annotations

from typing import Any

__all__ = ["validate"]

_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


def _type_ok(value: Any, expected: str | list[str]) -> bool:
    names = [expected] if isinstance(expected, str) else list(expected)
    for name in names:
        py = _TYPES.get(name)
        if py is None:
            return True  # unknown type keyword: don't penalize
        # bool is a subclass of int in Python; JSON keeps them apart.
        if isinstance(value, bool) and name in ("integer", "number"):
            continue
        if isinstance(value, py):
            return True
    return False


def validate(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    problems: list[str] = []
    expected_type = schema.get("type")
    if expected_type is not None and not _type_ok(value, expected_type):
        return [f"{path}: expected {expected_type}, got {type(value).__name__}"]

    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: {value!r} not in enum")

    if isinstance(value, dict):
        props: dict[str, Any] = schema.get("properties") or {}
        for key in schema.get("required") or []:
            if key not in value:
                problems.append(f"{path}: missing required {key!r}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    problems.append(f"{path}: unexpected property {key!r}")
        for key, sub in props.items():
            if key in value and isinstance(sub, dict):
                problems.extend(validate(value[key], sub, f"{path}.{key}"))

    if isinstance(value, list):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            problems.append(f"{path}: fewer than {schema['minItems']} items")
        items = schema.get("items")
        if isinstance(items, dict):
            for i, v in enumerate(value):
                problems.extend(validate(v, items, f"{path}[{i}]"))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            problems.append(f"{path}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            problems.append(f"{path}: {value} > maximum {schema['maximum']}")

    return problems
