"""VS Code REST Client (.http) serializer for generated API test cases."""

import json

from specprobe.exporter.utils import (
    build_query_string,
    extract_schema_properties,
    resolve_operation_method_and_path,
    substitute_path_params,
)
from specprobe.generator.models import GeneratedTestCase


def _build_request_block(test_case: GeneratedTestCase) -> str:
    """Serialize a single GeneratedTestCase into an RFC 7230 REST Client request block.

    Parameters
    ----------
    test_case : GeneratedTestCase
        The test case to format.

    Returns
    -------
    str
        Formatted request block including ### delimiter, metadata comments,
        request line, headers, and optional body.
    """
    lines: list[str] = ["###"]

    # Metadata comments
    lines.append(f"# @name {test_case.operation_id}")
    lines.append(f"# Operation: {test_case.operation_id}")

    if test_case.description and test_case.description.strip():
        desc_lines = test_case.description.strip().splitlines()
        lines.append(f"# Description: {desc_lines[0].strip()}")
        for extra_line in desc_lines[1:]:
            cleaned = extra_line.strip()
            if cleaned:
                lines.append(f"# {cleaned}")

    lines.append(f"# Expected Status: {test_case.response.status_code}")

    properties = extract_schema_properties(test_case.response.schema_shape)
    if properties:
        lines.append(f"# Expected Properties: {', '.join(properties)}")

    # Resolve HTTP method and path template
    method, path_template = resolve_operation_method_and_path(test_case)
    substituted_path = substitute_path_params(path_template, test_case.request.path_params)
    if not substituted_path.startswith("/"):
        substituted_path = "/" + substituted_path

    query_string = build_query_string(test_case.request.query_params)
    if query_string:
        target_url = f"{{{{baseUrl}}}}{substituted_path}?{query_string}"
    else:
        target_url = f"{{{{baseUrl}}}}{substituted_path}"

    lines.append(f"{method} {target_url} HTTP/1.1")

    # Headers (sorted for byte-identical determinism per Constitution Principle II)
    if test_case.request.headers:
        for header_name in sorted(test_case.request.headers.keys()):
            header_val = test_case.request.headers[header_name]
            lines.append(f"{header_name}: {header_val}")

    # Body
    if test_case.request.body is not None:
        lines.append("")
        if isinstance(test_case.request.body, str):
            lines.append(test_case.request.body)
        else:
            lines.append(json.dumps(test_case.request.body, indent=2, ensure_ascii=False))

    return "\n".join(lines)


def generate_http_document(
    test_cases: list[GeneratedTestCase],
    base_url: str = "http://localhost:8000",
) -> str:
    """Generate a VS Code REST Client (.http) plain-text document from test cases.

    Parameters
    ----------
    test_cases : list[GeneratedTestCase]
        List of generated test cases to serialize.
    base_url : str
        Target base URL embedded as the top-level '@baseUrl' variable.

    Returns
    -------
    str
        Complete .http document formatted with RFC 7230 request blocks.
        Returns empty string if test_cases is empty.
    """
    if not test_cases:
        return ""

    resolved_base_url = (
        base_url.strip().rstrip("/") if base_url and base_url.strip() else "http://localhost:8000"
    )

    header = f"@baseUrl = {resolved_base_url}"
    blocks = [_build_request_block(tc) for tc in test_cases]

    return f"{header}\n\n" + "\n\n".join(blocks) + "\n"
