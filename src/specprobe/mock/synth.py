"""Deterministic, zero-LLM JSON Schema Draft 7 mock payload synthesizer.

Produces a small, readable value that still satisfies the schema's own
constraints: objects include only `required` properties, and arrays contain
exactly one synthesized item. `const`/`enum`/`example`/`default`/`minimum` are
honored ahead of synthesis, in that order, so the result still validates and
prefers schema-declared literals over generated ones. Strings fall back to a
fixed representative value for a recognized `format`, or to `sample_<key>`
(the enclosing property's own key) otherwise; numbers without `minimum`
collapse to `0`.
"""

import re
from typing import Any

__all__ = ["synthesize_sample_from_schema"]

_LOCAL_REF_PATTERN = re.compile(r"^#/(\$defs|definitions)/([^/]+)$")

_FORMAT_SAMPLES: dict[str, str] = {
    "date-time": "2024-01-01T00:00:00Z",
    "date": "2024-01-01",
    "email": "user@example.com",
    "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "uri": "https://example.com/sample",
    "url": "https://example.com/sample",
    "ipv4": "203.0.113.1",
}


def synthesize_sample_from_schema(schema: dict[str, Any] | None) -> Any:
    """Synthesize a minimal JSON-serializable value conforming to `schema`.

    Returns `None` if `schema` is `None`.
    """
    if schema is None:
        return None
    return _synthesize(schema, schema, key=None)


def _synthesize(node: dict[str, Any], root: dict[str, Any], key: str | None) -> Any:
    ref = node.get("$ref")
    if isinstance(ref, str):
        return _synthesize(_resolve_local_ref(ref, root), root, key)

    if "const" in node:
        return node["const"]

    enum = node.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]

    if "example" in node:
        return node["example"]

    if "default" in node:
        return node["default"]

    node_type = node.get("type")
    if isinstance(node_type, list):
        node_type = node_type[0] if node_type else None
    if node_type is None:
        if "properties" in node or "required" in node:
            node_type = "object"
        elif "items" in node:
            node_type = "array"

    if node_type == "object":
        return _synthesize_object(node, root)
    if node_type == "array":
        return _synthesize_array(node, root, key)
    if node_type == "string":
        node_format = node.get("format")
        if isinstance(node_format, str) and node_format in _FORMAT_SAMPLES:
            return _FORMAT_SAMPLES[node_format]
        return f"sample_{key}" if key is not None else "sample_value"
    if node_type in ("integer", "number"):
        minimum = node.get("minimum")
        return minimum if minimum is not None else 0
    if node_type == "boolean":
        return False
    return None


def _synthesize_object(node: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    properties = node.get("properties", {})
    required = node.get("required", [])
    return {
        prop: _synthesize(properties[prop], root, key=prop) if prop in properties else None
        for prop in required
    }


def _synthesize_array(node: dict[str, Any], root: dict[str, Any], key: str | None) -> list[Any]:
    items = node.get("items")
    if isinstance(items, list):
        items = items[0] if items else None
    if not items:
        return []
    return [_synthesize(items, root, key)]


def _resolve_local_ref(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    match = _LOCAL_REF_PATTERN.match(ref)
    if not match:
        return {}
    container_key, name = match.group(1), match.group(2)
    return root.get(container_key, {}).get(name, {})
