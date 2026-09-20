"""Postman Collection v2.1.0 generator for generated API test cases."""

import json
import uuid
from typing import Any

from specprobe.exporter.utils import (
    build_query_string,
    extract_schema_properties,
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

    properties = extract_schema_properties(test_case.response.schema_shape)

    # TODO: schema_shape isn't validated as real JSON Schema at generation time
    # (see generator/prompt.py + generator/models.py), so this only checks property
    # presence via pm.expect(...).to.have.property(key). Revisit as
    # pm.response.to.have.jsonSchema(schema_shape) once schema_shape generation
    # is hardened to guarantee valid JSON Schema output.
    if properties:
        prop_lines = [
            "",
            'pm.test("Response has expected properties", function () {',
            "    var jsonData = pm.response.json();",
        ]
        for prop in properties:
            prop_lines.append(f'    pm.expect(jsonData).to.have.property("{prop}");')
        prop_lines.append("});")
        lines.extend(prop_lines)

    return lines


def _build_postman_item(test_case: GeneratedTestCase) -> dict[str, Any]:
    """Build a Postman request item from a GeneratedTestCase."""
    method, path_template = resolve_operation_method_and_path(test_case)
    substituted_path = substitute_path_params(path_template, test_case.request.path_params)
    if not substituted_path.startswith("/"):
        substituted_path = f"/{substituted_path}"

    # Build query list and full URL
    query_list = []
    if test_case.request.query_params:
        for k, v in test_case.request.query_params.items():
            if v is not None:
                query_list.append({"key": str(k), "value": str(v)})

    qs = build_query_string(test_case.request.query_params)
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

    # Headers
    header_list = []
    if test_case.request.headers:
        for k, v in test_case.request.headers.items():
            header_list.append(
                {
                    "key": str(k),
                    "value": str(v),
                    "type": "text",
                }
            )

    # Request description with operation_id traceability
    desc_lines = [f"Operation: {test_case.operation_id}"]
    if test_case.description:
        desc_lines.append(test_case.description)
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

    return {
        "info": {
            "_postman_id": postman_id,
            "name": resolved_name,
            "schema": POSTMAN_SCHEMA_URI,
            "description": "Generated by SpecProbe from OpenAPI specifications.",
        },
        "variable": [
            {
                "key": "baseUrl",
                "value": base_url,
                "type": "string",
            }
        ],
        "item": items,
    }
