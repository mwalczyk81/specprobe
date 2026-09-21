"""Postman Collection v2.1.0 generator for generated API test cases."""

import json
import uuid
from typing import Any

from specprobe.exporter.security import (
    SecurityResolver,
    format_postman_security_desc,
)
from specprobe.exporter.utils import (
    build_query_string,
    resolve_operation_method_and_path,
    substitute_path_params,
)
from specprobe.generator.models import GeneratedTestCase

POSTMAN_SCHEMA_URI = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"


def _build_test_script_lines(test_case: GeneratedTestCase) -> list[str]:
    """Generate JavaScript assertions for the Postman test script event."""
    lines: list[str] = [
        f'pm.test("Status code is {test_case.response.status_code}", function () {{',
        f"    pm.response.to.have.status({test_case.response.status_code});",
        "});",
    ]

    # Header presence assertions
    if test_case.response.headers:
        for header_name in sorted(test_case.response.headers.keys()):
            lines.extend(
                [
                    "",
                    f'pm.test("Header {header_name} is present", function () {{',
                    f'    pm.response.to.have.header("{header_name}");',
                    "});",
                ]
            )

    if test_case.response.schema_shape is not None:
        schema_raw = json.dumps(
            test_case.response.schema_shape,
            indent=4,
            ensure_ascii=False,
            sort_keys=True,
        )
        schema_lines_split = schema_raw.splitlines()
        schema_var_lines = ["    var schema = " + schema_lines_split[0]]
        for s_line in schema_lines_split[1:]:
            schema_var_lines.append("    " + s_line)
        schema_var_lines[-1] += ";"

        schema_lines = [
            "",
            'pm.test("Response matches JSON Schema", function () {',
            *schema_var_lines,
            "    pm.response.to.have.jsonSchema(schema);",
            "});",
        ]
        lines.extend(schema_lines)

    return lines


def _build_postman_item(test_case: GeneratedTestCase) -> dict[str, Any]:
    """Build a Postman request item from a GeneratedTestCase."""
    method, path_template = resolve_operation_method_and_path(test_case)
    substituted_path = substitute_path_params(path_template, test_case.request.path_params)
    if not substituted_path.startswith("/"):
        substituted_path = f"/{substituted_path}"

    is_negative_401 = getattr(test_case, "test_type", "positive") == "negative_auth_missing"
    is_negative_403 = getattr(test_case, "test_type", "positive") == "negative_auth_invalid"
    is_negative_404 = getattr(test_case, "test_type", "positive") == "negative_not_found"
    is_negative_400 = getattr(test_case, "test_type", "positive") == "negative_invalid_input"
    is_negative_auth = is_negative_401 or is_negative_403

    # Resolve security credentials
    resolved_creds = SecurityResolver.resolve_credentials(
        test_case.security,
        test_case.security_schemes,
    )

    # Build query dictionary (parameterize credentials for positive and negative input cases;
    # negative auth cases preserve raw queries)
    query_dict = dict(test_case.request.query_params) if test_case.request.query_params else {}
    if not is_negative_auth:
        for cred in resolved_creds:
            if cred.transport == "query":
                query_dict[cred.target_name] = cred.wire_value_template

    query_list = []
    if query_dict:
        for k, v in query_dict.items():
            if v is not None:
                query_list.append({"key": str(k), "value": str(v)})

    qs = build_query_string(query_dict)
    raw_url = f"{{{{baseUrl}}}}{substituted_path}"
    if qs:
        raw_url = f"{raw_url}?{qs}"

    path_segments = [seg for seg in substituted_path.strip("/").split("/") if seg]

    url_obj: dict[str, Any] = {
        "raw": raw_url,
        "host": ["{{baseUrl}}"],
        "path": path_segments,
    }
    if query_list:
        url_obj["query"] = query_list

    # Headers (parameterize credentials for positive and negative input cases;
    # negative auth cases preserve raw headers)
    headers_dict = dict(test_case.request.headers) if test_case.request.headers else {}
    if not is_negative_auth:
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

    header_list = []
    if headers_dict:
        for k, v in headers_dict.items():
            header_list.append(
                {
                    "key": str(k),
                    "value": str(v),
                    "type": "text",
                }
            )

    # Request description with operation_id traceability and security metadata
    desc_lines = [f"Operation: {test_case.operation_id}"]
    if test_case.description:
        desc_lines.append(test_case.description)
    if not is_negative_auth:
        for cred in resolved_creds:
            sec_desc = format_postman_security_desc(cred)
            if sec_desc:
                desc_lines.append(sec_desc)
    request_desc = "\n\n".join(desc_lines)

    request_obj: dict[str, Any] = {
        "method": method,
        "header": header_list,
        "url": url_obj,
        "description": request_desc,
    }

    # Body
    if test_case.request.body is not None:
        if isinstance(test_case.request.body, str):
            raw_body = test_case.request.body
        else:
            raw_body = json.dumps(test_case.request.body, indent=2, ensure_ascii=False)

        request_obj["body"] = {
            "mode": "raw",
            "raw": raw_body,
            "options": {
                "raw": {
                    "language": "json",
                }
            },
        }

    # Tests script event
    script_lines = _build_test_script_lines(test_case)
    event_obj = [
        {
            "listen": "test",
            "script": {
                "type": "text/javascript",
                "exec": script_lines,
            },
        }
    ]

    item_name = test_case.description.strip() if test_case.description else test_case.operation_id
    if is_negative_401 and not item_name.startswith("[401]"):
        item_name = f"[401] {item_name}"
    elif is_negative_403 and not item_name.startswith("[403]"):
        item_name = f"[403] {item_name}"
    elif is_negative_404 and not item_name.startswith("[404]"):
        item_name = f"[404] {item_name}"
    elif is_negative_400 and not item_name.startswith("[400]"):
        item_name = f"[400] {item_name}"

    return {
        "name": item_name,
        "request": request_obj,
        "event": event_obj,
    }


def generate_postman_collection(
    test_cases: list[GeneratedTestCase],
    collection_name: str | None = None,
    base_url: str = "http://localhost:8000",
) -> dict[str, Any]:
    """Generate a Postman Collection v2.1.0 data structure from test cases.

    Parameters
    ----------
    test_cases : list[GeneratedTestCase]
        List of generated API test cases to transform.
    collection_name : str | None
        Name for the collection. If omitted, defaults to 'SpecProbe Generated Collection'.
    base_url : str
        Target base URL embedded as collection variable 'baseUrl'.

    Returns
    -------
    dict[str, Any]
        Dictionary representation of Postman Collection v2.1.0 conforming to schema.
    """
    resolved_name = (
        collection_name.strip()
        if collection_name and collection_name.strip()
        else "SpecProbe Generated Collection"
    )
    postman_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"specprobe:{resolved_name}"))

    folders: dict[str, list[dict[str, Any]]] = {}
    root_items: list[dict[str, Any]] = []

    for tc in test_cases:
        item = _build_postman_item(tc)
        if tc.tags and tc.tags[0].strip():
            primary_tag = tc.tags[0].strip()
            if primary_tag not in folders:
                folders[primary_tag] = []
            folders[primary_tag].append(item)
        else:
            root_items.append(item)

    items: list[dict[str, Any]] = []
    for tag_name, folder_items in folders.items():
        items.append(
            {
                "name": tag_name,
                "item": folder_items,
            }
        )
    items.extend(root_items)

    # Aggregate all unique security credentials across test cases
    seen_vars: set[str] = set()
    sec_variables: list[dict[str, Any]] = []

    for tc in test_cases:
        test_type = getattr(tc, "test_type", "positive")
        if test_type in ("negative_auth_missing", "negative_auth_invalid"):
            continue
        tc_creds = SecurityResolver.resolve_credentials(tc.security, tc.security_schemes)
        for cred in tc_creds:
            if cred.variable_name not in seen_vars:
                seen_vars.add(cred.variable_name)
                sec_variables.append(
                    {
                        "key": cred.variable_name,
                        "value": cred.default_placeholder,
                        "type": "string",
                    }
                )

    # Sort security variables alphabetically by key for determinism
    sec_variables.sort(key=lambda v: v["key"])

    collection_variables = [
        {
            "key": "baseUrl",
            "value": base_url,
            "type": "string",
        },
        *sec_variables,
    ]

    return {
        "info": {
            "_postman_id": postman_id,
            "name": resolved_name,
            "schema": POSTMAN_SCHEMA_URI,
            "description": "Generated by SpecProbe from OpenAPI specifications.",
        },
        "variable": collection_variables,
        "item": items,
    }
