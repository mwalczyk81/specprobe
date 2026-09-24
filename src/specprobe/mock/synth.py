"""Deterministic, zero-LLM JSON Schema Draft 7 mock payload synthesizer.

Produces a small, readable value that still satisfies the schema's own
constraints: objects include only `required` properties, and arrays contain
exactly one synthesized item. `allOf` branches are merged into their parent,
and `anyOf`/`oneOf` contribute their first branch. `const`/`enum`/`example`/
`default`/`minimum` are honored ahead of synthesis, in that order, so the result
still validates and prefers schema-declared literals over generated ones.
Strings fall back to a fixed representative value for a recognized `format`, or
to `sample_<key>` (the enclosing property's own key) otherwise, then are fitted
to `minLength`/`maxLength`; a `pattern` the fallback doesn't match is satisfied
by a string built from the regex itself. Numbers without `minimum` collapse to
`0`.
"""

import importlib
import re
from typing import Any

__all__ = ["synthesize_sample_from_schema"]

# CPython's own regex parser (stable across 3.11+, but private and unstubbed in
# typeshed). Used only to build a sample string for a `pattern`; any surprise in
# its output is caught by re-checking the sample against the pattern.
_regex_parser: Any = importlib.import_module("re._parser")

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

    node = _merge_composition(node, root)

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
        return _synthesize_string(node, key)
    if node_type in ("integer", "number"):
        minimum = node.get("minimum")
        return minimum if minimum is not None else 0
    if node_type == "boolean":
        return False
    return None


def _merge_composition(node: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    """Fold `allOf` branches, and the first `anyOf`/`oneOf` branch, into one schema.

    `properties` and `required` are unioned; any other keyword is taken from the
    first schema that declares it, with the parent's own keywords winning.
    """
    branches: list[Any] = []
    all_of = node.get("allOf")
    if isinstance(all_of, list):
        branches.extend(all_of)
    for keyword in ("anyOf", "oneOf"):
        alternatives = node.get(keyword)
        if isinstance(alternatives, list) and alternatives:
            branches.append(alternatives[0])
    if not branches:
        return node

    merged = {k: v for k, v in node.items() if k not in ("allOf", "anyOf", "oneOf")}
    for branch in branches:
        if not isinstance(branch, dict):
            continue
        ref = branch.get("$ref")
        if isinstance(ref, str):
            branch = _resolve_local_ref(ref, root)
        branch = _merge_composition(branch, root)
        for branch_key, value in branch.items():
            if branch_key == "properties" and isinstance(value, dict):
                merged["properties"] = {**value, **merged.get("properties", {})}
            elif branch_key == "required" and isinstance(value, list):
                merged["required"] = list(dict.fromkeys([*merged.get("required", []), *value]))
            else:
                merged.setdefault(branch_key, value)
    return merged


def _synthesize_string(node: dict[str, Any], key: str | None) -> str:
    node_format = node.get("format")
    if isinstance(node_format, str) and node_format in _FORMAT_SAMPLES:
        value = _FORMAT_SAMPLES[node_format]
    else:
        value = f"sample_{key}" if key is not None else "sample_value"

    pattern = node.get("pattern")
    if isinstance(pattern, str) and not _matches_pattern(pattern, value):
        pattern_value = _sample_for_pattern(pattern)
        if pattern_value is not None:
            return pattern_value

    min_length = node.get("minLength")
    if isinstance(min_length, int) and len(value) < min_length:
        value = value + "x" * (min_length - len(value))
    max_length = node.get("maxLength")
    if isinstance(max_length, int) and len(value) > max_length:
        value = value[:max_length]
    return value


def _matches_pattern(pattern: str, value: str) -> bool:
    try:
        return re.search(pattern, value) is not None
    except re.error:
        return False


def _sample_for_pattern(pattern: str) -> str | None:
    """Build the shortest string the regex accepts, or None for unsupported syntax.

    JSON Schema patterns are ECMA-262 regexes, which Python's parser accepts for
    the common subset (anchors, classes, quantifiers, groups, alternation). The
    result is re-checked against the pattern, so anything the walk below gets
    wrong is discarded rather than emitted.
    """
    try:
        sample = _render_regex(_regex_parser.parse(pattern))
    except (re.error, ValueError, TypeError):
        return None
    return sample if _matches_pattern(pattern, sample) else None


_CATEGORY_SAMPLES = {
    "CATEGORY_DIGIT": "0",
    "CATEGORY_NOT_DIGIT": "a",
    "CATEGORY_WORD": "a",
    "CATEGORY_NOT_WORD": "-",
    "CATEGORY_SPACE": " ",
    "CATEGORY_NOT_SPACE": "a",
}
_NEGATED_CLASS_CANDIDATES = "aA0_- .x"


def _render_regex(tokens: Any) -> str:
    out: list[str] = []
    for op, arg in tokens:
        name = str(op)
        if name == "LITERAL":
            out.append(chr(arg))
        elif name == "NOT_LITERAL":
            out.append("a" if arg != ord("a") else "b")
        elif name == "ANY":
            out.append("a")
        elif name == "IN":
            out.append(_render_class(arg))
        elif name in ("MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT"):
            minimum, _maximum, sub_tokens = arg
            out.append(_render_regex(sub_tokens) * minimum)
        elif name in ("SUBPATTERN", "ATOMIC_GROUP"):
            out.append(_render_regex(arg[-1]))
        elif name == "BRANCH":
            out.append(_render_regex(arg[1][0]))
        elif name == "AT":
            continue
        else:
            raise ValueError(f"unsupported regex construct {name}")
    return "".join(out)


def _render_class(items: Any) -> str:
    if items and str(items[0][0]) == "NEGATE":
        excluded = items[1:]
        for candidate in _NEGATED_CLASS_CANDIDATES:
            if not _class_contains(excluded, candidate):
                return candidate
        raise ValueError("no candidate character outside negated class")
    op, arg = items[0]
    name = str(op)
    if name == "LITERAL":
        return chr(arg)
    if name == "RANGE":
        return chr(arg[0])
    if name == "CATEGORY" and str(arg) in _CATEGORY_SAMPLES:
        return _CATEGORY_SAMPLES[str(arg)]
    raise ValueError(f"unsupported character class member {name}")


def _class_contains(items: Any, char: str) -> bool:
    code = ord(char)
    is_word = char.isalnum() or char == "_"
    category_checks = {
        "CATEGORY_DIGIT": char.isdigit(),
        "CATEGORY_NOT_DIGIT": not char.isdigit(),
        "CATEGORY_WORD": is_word,
        "CATEGORY_NOT_WORD": not is_word,
        "CATEGORY_SPACE": char.isspace(),
        "CATEGORY_NOT_SPACE": not char.isspace(),
    }
    for op, arg in items:
        name = str(op)
        if name == "LITERAL" and arg == code:
            return True
        if name == "RANGE" and arg[0] <= code <= arg[1]:
            return True
        if name == "CATEGORY" and category_checks.get(str(arg), True):
            return True
    return False


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
