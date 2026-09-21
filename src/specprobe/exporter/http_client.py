"""VS Code REST Client (.http) serializer for generated API test cases."""

import json

from specprobe.exporter.security import (
    SecurityResolver,
    format_security_comment,
)
from specprobe.exporter.utils import (
    build_query_string,
    format_schema_signature,
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
    is_negative_401 = getattr(test_case, "test_type", "positive") == "negative_auth_missing"
    is_negative_403 = getattr(test_case, "test_type", "positive") == "negative_auth_invalid"
    is_negative_404 = getattr(test_case, "test_type", "positive") == "negative_not_found"
    is_negative_400 = getattr(test_case, "test_type", "positive") == "negative_invalid_input"
    is_negative_auth = is_negative_401 or is_negative_403

    lines: list[str] = ["###"]

    # Metadata comments
    if is_negative_401:
        lines.append(f"# @name {test_case.operation_id}_401")
    elif is_negative_403:
        lines.append(f"# @name {test_case.operation_id}_403")
    elif is_negative_404:
        lines.append(f"# @name {test_case.operation_id}_404")
    elif is_negative_400:
        lines.append(f"# @name {test_case.operation_id}_400")
    else:
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

    schema_sig = format_schema_signature(test_case.response.schema_shape)
    if schema_sig:
        lines.append(schema_sig)

    # Resolve security credentials (only parameterize for positive and negative input test cases)
    resolved_creds = []
    if not is_negative_auth:
        resolved_creds = SecurityResolver.resolve_credentials(
            test_case.security,
            test_case.security_schemes,
        )
        for cred in resolved_creds:
            sec_comments = format_security_comment(cred)
            lines.extend(sec_comments)

    # Resolve HTTP method and path template
    method, path_template = resolve_operation_method_and_path(test_case)
    substituted_path = substitute_path_params(path_template, test_case.request.path_params)
    if not substituted_path.startswith("/"):
        substituted_path = "/" + substituted_path

    # Query string with security parameterization
    query_dict = dict(test_case.request.query_params) if test_case.request.query_params else {}
    for cred in resolved_creds:
        if cred.transport == "query":
            query_dict[cred.target_name] = cred.wire_value_template

    query_string = build_query_string(query_dict)
    if query_string:
        target_url = f"{{{{baseUrl}}}}{substituted_path}?{query_string}"
    else:
        target_url = f"{{{{baseUrl}}}}{substituted_path}"

    lines.append(f"{method} {target_url} HTTP/1.1")

    # Headers with security parameterization (sorted for determinism)
    headers_dict = dict(test_case.request.headers) if test_case.request.headers else {}
    for cred in resolved_creds:
        if cred.transport == "header":
            existing_key = next(
                (k for k in headers_dict if k.lower() == cred.target_name.lower()),
                None,
            )
            if existing_key:
                headers_dict[existing_key] = cred.wire_value_template
            else:
                headers_dict[cred.target_name] = cred.wire_value_template

    if headers_dict:
        for header_name in sorted(headers_dict.keys()):
            header_val = headers_dict[header_name]
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

    # Collect all unique security credentials across test cases for file variables
    seen_vars: set[str] = set()
    sec_vars: list[str] = []

    for tc in test_cases:
        test_type = getattr(tc, "test_type", "positive")
        if test_type in ("negative_auth_missing", "negative_auth_invalid"):
            continue
        tc_creds = SecurityResolver.resolve_credentials(tc.security, tc.security_schemes)
        for cred in tc_creds:
            if cred.variable_name not in seen_vars:
                seen_vars.add(cred.variable_name)
                sec_vars.append(f"@{cred.variable_name} = {cred.default_placeholder}")

    # Sort security file variables alphabetically by variable name for determinism
    sec_vars.sort()

    header_lines = [f"@baseUrl = {resolved_base_url}", *sec_vars]
    header = "\n".join(header_lines)
    blocks = [_build_request_block(tc) for tc in test_cases]

    return f"{header}\n\n" + "\n\n".join(blocks) + "\n"
