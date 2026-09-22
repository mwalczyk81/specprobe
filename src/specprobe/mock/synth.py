"""Deterministic, zero-LLM JSON Schema Draft 7 mock payload synthesizer.

Produces the smallest value that still satisfies the schema's own constraints:
primitives collapse to their minimal representable value (empty string, 0,
false, null), objects include only `required` properties, and arrays contain
exactly one synthesized item. `const`/`enum`/`minimum` are honored so the
result still validates, since a plain empty/zero value would violate those
constraints.
"""

import re
from typing import Any

__all__ = ["synthesize_sample_from_schema"]

_LOCAL_REF_PATTERN = re.compile(r"^#/(\$defs|definitions)/([^/]+)$")


def synthesize_sample_from_schema(schema: dict[str, Any] | None) -> Any:
    """Synthesize a minimal JSON-serializable value conforming to `schema`.

    Returns `None` if `schema` is `None`.
    """
    if schema is None:
        return None
    return _synthesize(schema, schema)


def _synthesize(node: dict[str, Any], root: dict[str, Any]) -> Any:
    ref = node.get("$ref")
    if isinstance(ref, str):
        return _synthesize(_resolve_local_ref(ref, root), root)

    if "const" in node:
        return node["const"]

    enum = node.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]

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
        return _synthesize_array(node, root)
    if node_type == "string":
        return ""
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
        key: _synthesize(properties[key], root) if key in properties else None for key in required
    }


def _synthesize_array(node: dict[str, Any], root: dict[str, Any]) -> list[Any]:
    items = node.get("items")
    if isinstance(items, list):
        items = items[0] if items else None
    if not items:
        return []
    return [_synthesize(items, root)]


def _resolve_local_ref(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    match = _LOCAL_REF_PATTERN.match(ref)
    if not match:
        return {}
    container_key, name = match.group(1), match.group(2)
    return root.get(container_key, {}).get(name, {})
