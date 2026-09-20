"""URL parameter substitution, encoding, and path utilities for test exporters."""

import re
import urllib.parse
from typing import Any

from specprobe.generator.models import GeneratedTestCase


def substitute_path_params(path_template: str, path_params: dict[str, Any] | None) -> str:
    """Substitute path parameters into URL template using RFC 3986 encoding.

    Parameters
    ----------
    path_template : str
        URL path template containing placeholders, e.g. '/pets/{petId}'.
    path_params : dict[str, Any] | None
        Dictionary mapping parameter names to concrete values.

    Returns
    -------
    str
        Resolved path with URL-encoded parameter values.
    """
    if not path_template:
        return "/"

    if not path_params:
        return path_template

    def _replace(match: re.Match[str]) -> str:
        param_name = match.group(1)
        if param_name in path_params:
            val = path_params[param_name]
            # Use safe="" to strictly encode all reserved characters (spaces, slashes, etc.)
            return urllib.parse.quote(str(val), safe="")
        return match.group(0)

    # Match placeholders formatted as {param_name}
    resolved = re.sub(r"\{([a-zA-Z0-9_\-\.]+)\}", _replace, path_template)
    return resolved


def build_query_string(query_params: dict[str, Any] | None) -> str:
    """Encode query parameters into a standard query string.

    Parameters
    ----------
    query_params : dict[str, Any] | None
        Key-value dictionary of query parameters.

    Returns
    -------
    str
        Encoded query string, or empty string if no parameters provided.
    """
    if not query_params:
        return ""
    # Filter out None values
    filtered = {k: v for k, v in query_params.items() if v is not None}
    if not filtered:
        return ""
    return urllib.parse.urlencode(filtered, doseq=True)


def resolve_operation_method_and_path(test_case: GeneratedTestCase) -> tuple[str, str]:
    """Determine HTTP method and endpoint path template for a test case.

    Inspects `test_case.request.method` and `test_case.request.path` first.
    If absent, falls back to parsing method/path from `operation_id` or sensible defaults.

    Parameters
    ----------
    test_case : GeneratedTestCase
        The test case to inspect.

    Returns
    -------
    tuple[str, str]
        (uppercase_http_method, path_template)
    """
    method = test_case.request.method
    path = test_case.request.path

    if method and path:
        return method.strip().upper(), path.strip()

    op_id = test_case.operation_id.strip()

    # Check for METHOD_path patterns (e.g. GET_pets_petId or delete_pets_pet_id)
    known_methods = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")
    for km in known_methods:
        if op_id.upper().startswith(f"{km}_"):
            inferred_method = km
            remainder = op_id[len(km) + 1 :].strip("_")
            inferred_path = f"/{remainder.replace('_', '/')}" if remainder else "/"
            return method.upper() if method else inferred_method, path if path else inferred_path

    # Fallback default
    if method:
        fallback_method = method.upper()
    elif test_case.request.body is not None:
        fallback_method = "POST"
    else:
        fallback_method = "GET"
    fallback_path = path if path else f"/{op_id}"
    return fallback_method, fallback_path


def extract_schema_properties(schema_shape: Any) -> list[str]:
    """Extract top-level property names from a schema_shape structure.

    Parameters
    ----------
    schema_shape : Any
        Expected schema dictionary, list of properties, or None.

    Returns
    -------
    list[str]
        List of distinct property names extracted from the shape.
    """
    if not schema_shape:
        return []

    if isinstance(schema_shape, dict):
        props = schema_shape.get("properties")
        if isinstance(props, list):
            return [str(p) for p in props if p]
        elif isinstance(props, dict):
            return [str(k) for k in props.keys()]

        # Check if items.properties exists (e.g. array of objects)
        items = schema_shape.get("items")
        if isinstance(items, dict):
            item_props = items.get("properties")
            if isinstance(item_props, list):
                return [str(p) for p in item_props if p]
            elif isinstance(item_props, dict):
                return [str(k) for k in item_props.keys()]

        # If schema_shape is a plain key-value dict representing object properties directly
        excluded_keys = {"type", "required", "title", "description", "$schema", "items"}
        candidate_keys = [str(k) for k in schema_shape.keys() if k not in excluded_keys]
        if candidate_keys:
            return candidate_keys
    elif isinstance(schema_shape, list):
        return [str(p) for p in schema_shape if isinstance(p, (str, int))]

    return []
