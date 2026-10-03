"""Planted-change regression harness for `specprobe diff`.

Builds a small accounts-style OpenAPI spec, applies a known set of mutations, and asserts the
engine reports exactly the expected changes (and nothing else). Mirrors the shapes that matter on
real specs: shared $ref schemas, allOf, nested objects, array items, enums, path-parameter renames.
"""

import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from specprobe.diff.engine import DiffEngine

Spec = dict[str, Any]


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _resp(schema: dict[str, Any] | None = None, description: str = "OK") -> dict[str, Any]:
    out: dict[str, Any] = {"description": description}
    if schema is not None:
        out["content"] = {"application/json": {"schema": schema}}
    return out


def _id_param(schema: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": "id", "in": "path", "required": True, "schema": schema or _ref("accountId")}


def _base_spec() -> Spec:
    return {
        "openapi": "3.0.3",
        "info": {"title": "Accounts", "version": "1"},
        "paths": {
            "/legacy": {"get": {"responses": {"200": _resp()}}},
            "/accounts/{id}": {
                "get": {
                    "parameters": [_id_param()],
                    "responses": {"200": _resp(_ref("accountResponse"))},
                }
            },
            "/accounts/{id}/balances": {
                "get": {
                    "parameters": [_id_param()],
                    "responses": {
                        "200": _resp({"type": "array", "items": _ref("balance")}),
                        "404": _resp(description="Not found"),
                    },
                },
                "put": {
                    "parameters": [_id_param()],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"type": "array", "items": _ref("balanceUpsert")}
                            }
                        },
                    },
                    "responses": {"200": _resp({"type": "array", "items": _ref("balance")})},
                },
            },
            "/accounts/{id}/number": {
                "get": {
                    "parameters": [_id_param()],
                    "responses": {
                        "200": _resp({"type": "object", "properties": {"n": {"type": "string"}}}),
                        "400": _resp(description="Bad request"),
                    },
                }
            },
            "/accounts/{id}/transactions/images": {
                "get": {
                    "parameters": [_id_param()],
                    "responses": {"200": _resp(_ref("txnImages"))},
                }
            },
            "/accounts/{id}/details": {
                "get": {
                    "parameters": [_id_param()],
                    "responses": {"200": _resp(_ref("detail"))},
                }
            },
            "/accounts/{id}/stops": {
                "post": {
                    "parameters": [_id_param()],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": _ref("stopChecks")}},
                    },
                    "responses": {"202": _resp(_ref("stopChecks"))},
                }
            },
            "/accounts/{id}/summary": {
                "get": {
                    "summary": "Account summary",
                    "parameters": [_id_param()],
                    "responses": {
                        "200": _resp({"type": "object", "properties": {"s": {"type": "string"}}})
                    },
                }
            },
            "/accounts/{id}/audit-log": {
                "get": {
                    "parameters": [_id_param({"type": "string"})],
                    "responses": {
                        "200": _resp({"type": "object", "properties": {"log": {"type": "string"}}})
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "accountId": {"type": "string", "maxLength": 128},
                "amount": {
                    "type": "object",
                    "properties": {"currency": {"type": "string"}, "value": {"type": "number"}},
                    "required": ["currency", "value"],
                },
                "balance": {
                    "type": "object",
                    "properties": {
                        "accountId": _ref("accountId"),
                        "amount": _ref("amount"),
                        "dateTime": {"type": "string", "format": "date-time"},
                        "type": {"type": "string"},
                    },
                    "required": ["accountId", "amount", "dateTime", "type"],
                },
                "balanceUpsert": {
                    "type": "object",
                    "properties": {
                        "amount": _ref("amount"),
                        "dateTime": {"type": "string", "format": "date-time"},
                        "type": {"type": "string"},
                    },
                    "required": ["amount", "type"],
                },
                "accountBase": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["active", "inactive"]},
                        "description": {"type": "string", "description": "Free text"},
                    },
                },
                "accountResponse": {
                    "allOf": [
                        _ref("accountBase"),
                        {
                            "type": "object",
                            "properties": {"id": _ref("accountId"), "number": {"type": "string"}},
                            "required": ["id", "number"],
                        },
                    ]
                },
                "txnImages": {
                    "type": "object",
                    "properties": {
                        "images": {"type": "array", "items": {"type": "string"}},
                        "transaction": {
                            "type": "object",
                            "properties": {
                                "amount": _ref("amount"),
                                "customerReferenceNumber": {"type": "string"},
                                "dateTime": {"type": "string"},
                            },
                            "required": ["amount", "customerReferenceNumber", "dateTime"],
                        },
                    },
                    "required": ["images"],
                },
                "amountDetail": {
                    "allOf": [
                        {
                            "type": "object",
                            "properties": {"code": {"type": "string"}},
                            "required": ["code"],
                        },
                        {
                            "type": "object",
                            "properties": {
                                "applicationPeriod": {
                                    "type": "string",
                                    "enum": ["total", "yearToDate"],
                                }
                            },
                        },
                    ]
                },
                "detail": {
                    "type": "object",
                    "properties": {
                        "accountId": _ref("accountId"),
                        "amounts": {"type": "array", "items": _ref("amountDetail")},
                    },
                },
                "stopChecks": {
                    "type": "object",
                    "properties": {
                        "checkNumbersStart": {"type": "integer", "minimum": 1},
                        "reason": {"type": "string"},
                    },
                    "required": ["checkNumbersStart"],
                },
            }
        },
    }


def _rename_path_param(spec: Spec, old_path: str, new_path: str, new_name: str) -> None:
    item = spec["paths"].pop(old_path)
    for op in item.values():
        for param in op.get("parameters", []):
            if param["in"] == "path":
                param["name"] = new_name
    spec["paths"][new_path] = item


def _mutated_spec() -> Spec:
    new = deepcopy(_base_spec())
    paths, schemas = new["paths"], new["components"]["schemas"]

    del paths["/legacy"]  # removed operation
    paths["/accounts/{id}"]["delete"] = {  # added operation
        "parameters": [_id_param()],
        "responses": {"204": _resp(description="Deleted")},
    }
    _rename_path_param(new, "/accounts/{id}/summary", "/accounts/{accountId}/summary", "accountId")
    schemas["balanceUpsert"]["required"].append("dateTime")  # new required request property
    del schemas["balance"]["properties"]["dateTime"]  # response property removed (shared schema)
    schemas["balance"]["required"].remove("dateTime")
    schemas["stopChecks"]["properties"]["checkNumbersStart"]["type"] = "string"  # type change
    schemas["accountBase"]["properties"]["status"]["enum"].remove("inactive")  # enum value removed
    del paths["/accounts/{id}/number"]["get"]["responses"]["200"]  # success status removed
    del paths["/accounts/{id}/balances"]["get"]["responses"]["404"]  # non-success removal: silent
    txn = schemas["txnImages"]["properties"]["transaction"]  # depth-3 response property removed
    del txn["properties"]["customerReferenceNumber"]
    txn["required"].remove("customerReferenceNumber")
    del schemas["amountDetail"]["allOf"][1]["properties"][
        "applicationPeriod"
    ]  # allOf + items, deep
    # Rename AND retype a path param: exactly one type_changed, no "newly required" false positive.
    _rename_path_param(
        new, "/accounts/{id}/audit-log", "/accounts/{accountId}/audit-log", "accountId"
    )
    paths["/accounts/{accountId}/audit-log"]["get"]["parameters"][0]["schema"] = {"type": "integer"}
    # Genuinely new required query parameter.
    paths["/accounts/{id}/details"]["get"]["parameters"].append(
        {"name": "asOf", "in": "query", "required": True, "schema": {"type": "string"}}
    )
    # Cosmetic edits and a new optional response field: all silent.
    paths["/accounts/{accountId}/summary"]["get"]["summary"] = "Reworded summary"
    schemas["amount"]["description"] = "Edited description"
    schemas["accountBase"]["properties"]["nickname"] = {"type": "string"}
    return new


EXPECTED = Counter(
    {
        ("operation_removed", "GET", "/legacy"): 1,
        ("operation_added", "DELETE", "/accounts/{id}"): 1,
        ("required_request_property_added", "PUT", "/accounts/{id}/balances"): 1,
        ("response_property_removed", "GET", "/accounts/{id}/balances"): 1,
        ("response_property_removed", "PUT", "/accounts/{id}/balances"): 1,
        (
            "type_changed",
            "POST",
            "/accounts/{id}/stops",
        ): 2,  # request + response both use stopChecks
        # Direction-agnostic per the v1 rule; revisit if enum removal becomes direction-aware.
        ("enum_value_removed", "GET", "/accounts/{id}"): 1,
        ("response_status_removed", "GET", "/accounts/{id}/number"): 1,
        ("response_property_removed", "GET", "/accounts/{id}/transactions/images"): 1,
        ("response_property_removed", "GET", "/accounts/{id}/details"): 1,
        ("required_request_property_added", "GET", "/accounts/{id}/details"): 1,
        ("type_changed", "GET", "/accounts/{id}/audit-log"): 1,
    }
)


def _engine(old: Spec, new: Spec, via: str, tmp_path: Path) -> DiffEngine:
    if via == "dict":
        return DiffEngine(old_spec=deepcopy(old), new_spec=deepcopy(new))
    old_file, new_file = tmp_path / "old.json", tmp_path / "new.json"
    old_file.write_text(json.dumps(old))
    new_file.write_text(json.dumps(new))
    return DiffEngine(old_spec=old_file, new_spec=new_file)


@pytest.mark.parametrize("via", ["dict", "file"])
def test_identical_specs_produce_no_changes(via: str, tmp_path: Path) -> None:
    base = _base_spec()
    assert list(_engine(base, base, via, tmp_path).diff()) == []


@pytest.mark.parametrize("via", ["dict", "file"])
def test_planted_changes_are_reported_exactly(via: str, tmp_path: Path) -> None:
    engine = _engine(_base_spec(), _mutated_spec(), via, tmp_path)
    records = list(engine.diff())

    got = Counter((r.change_type.value, r.method, r.path) for r in records)
    assert got == EXPECTED

    for record in records:
        assert record.breaking is (record.change_type.value != "operation_added")
    assert engine.get_summary().total_changes == sum(EXPECTED.values())
    assert engine.get_summary().has_breaking_changes is True
