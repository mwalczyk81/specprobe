"""Unit tests for JSON Schema Draft 7 hardening and self-correcting retry in test generation."""

import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from specprobe.chunker.models import ChunkMetadata, OperationChunk
from specprobe.generator.engine import GenerationEngine
from specprobe.generator.models import ResponseAssertion


def test_valid_draft7_schema():
    """Verify that a valid Draft 7 JSON Schema passes validation in ResponseAssertion."""
    valid_schema = {
        "type": "object",
        "required": ["id", "name"],
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
            "tag": {"type": "string"},
        },
    }
    assertion = ResponseAssertion(status_code=200, schema_shape=valid_schema)
    assert assertion.schema_shape == valid_schema


def test_valid_draft7_array_schema():
    """Verify that an array schema adhering to Draft 7 passes validation."""
    valid_array_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
            },
            "required": ["id"],
        },
    }
    assertion = ResponseAssertion(status_code=200, schema_shape=valid_array_schema)
    assert assertion.schema_shape == valid_array_schema


def test_none_schema_allowed():
    """Verify that schema_shape=None is permitted for bodyless responses."""
    assertion = ResponseAssertion(status_code=204, schema_shape=None)
    assert assertion.schema_shape is None


def test_invalid_schema_type_fails():
    """Verify that non-dict, non-None schema_shape raises ValidationError."""
    with pytest.raises(ValidationError) as excinfo:
        ResponseAssertion(status_code=200, schema_shape="invalid_string_schema")  # type: ignore[arg-type]
    assert "schema_shape" in str(excinfo.value)


def test_invalid_draft7_meta_schema_fails():
    """Verify that a schema violating JSON Schema Draft 7 meta-schema raises ValidationError."""
    invalid_schema = {
        "type": "not_a_valid_json_schema_type",
    }
    with pytest.raises(ValidationError) as excinfo:
        ResponseAssertion(status_code=200, schema_shape=invalid_schema)
    assert "Invalid JSON Schema Draft 7" in str(excinfo.value) or "schema_shape" in str(
        excinfo.value
    )


def test_bare_ref_rejected():
    """Verify that a bare unresolved $ref pointer without local definitions is rejected
    with the SPECIFIC unresolvable-$ref message, not the generic "no meaningful content"
    message. This is a regression guard: the "no meaningful content" check must run
    after the $ref-resolution check, otherwise a bare {"$ref": ...} schema (whose only
    top-level key is "$ref") gets the vague message instead of one that actually tells
    the self-correcting retry what's wrong -- which produces worse retry prompts and
    more double-failures in practice.
    """
    bare_ref = {"$ref": "#/components/schemas/Pet"}
    with pytest.raises(ValidationError) as excinfo:
        ResponseAssertion(status_code=200, schema_shape=bare_ref)
    message = str(excinfo.value)
    assert "unresolvable $ref pointer" in message
    assert "no meaningful validation content" not in message


def test_local_ref_only_schema_allowed():
    """Verify a schema whose only top-level content is a $ref that resolves to a local
    $defs entry is accepted -- a resolving "$ref" is itself meaningful validation
    content, not just metadata to be rejected alongside unused "$defs".
    """
    local_ref_schema = {
        "$ref": "#/$defs/Pet",
        "$defs": {
            "Pet": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
                "required": ["id", "name"],
            }
        },
    }
    assertion = ResponseAssertion(status_code=200, schema_shape=local_ref_schema)
    assert assertion.schema_shape == local_ref_schema


def test_nested_ref_in_items_rejected():
    """Verify an OpenAPI-relative $ref nested inside 'items' (array-of-object responses)
    is rejected, not just a bare top-level $ref. This is the case that slips past a
    naive top-level-only check: {"type": "array", "items": {"$ref": "#/components/schemas/Pet"}}
    is syntactically valid Draft 7, but the $ref can never resolve on its own, so Postman's
    Ajv engine would throw at runtime for every request exercising this schema.
    """
    nested_unresolvable_ref = {
        "type": "array",
        "items": {"$ref": "#/components/schemas/Pet"},
    }
    with pytest.raises(ValidationError) as excinfo:
        ResponseAssertion(status_code=200, schema_shape=nested_unresolvable_ref)
    assert "unresolvable" in str(excinfo.value) or "schema_shape" in str(excinfo.value)


def test_nested_ref_in_properties_rejected():
    """Verify an OpenAPI-relative $ref nested inside 'properties' is rejected."""
    nested_unresolvable_ref = {
        "type": "object",
        "properties": {"pet": {"$ref": "#/components/schemas/Pet"}},
    }
    with pytest.raises(ValidationError):
        ResponseAssertion(status_code=200, schema_shape=nested_unresolvable_ref)


def test_schema_with_defs_and_nested_ref_in_items_allowed():
    """Verify a local '$defs' ref nested inside 'items' (the correct way to write an
    array-of-referenced-object schema) is accepted.
    """
    schema_with_local_defs = {
        "type": "array",
        "$defs": {
            "Pet": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
                "required": ["id", "name"],
            }
        },
        "items": {"$ref": "#/$defs/Pet"},
    }
    assertion = ResponseAssertion(status_code=200, schema_shape=schema_with_local_defs)
    assert assertion.schema_shape == schema_with_local_defs


def test_defs_only_schema_with_no_meaningful_content_rejected():
    """Verify a schema_shape containing only an unreferenced '$defs' block (no 'type',
    'properties', or 'items' actually using it) is rejected as a no-op assertion, even
    though it's syntactically valid Draft 7.
    """
    defs_only_schema = {
        "$defs": {
            "Integer": {"type": "integer", "format": "int64"},
        }
    }
    with pytest.raises(ValidationError) as excinfo:
        ResponseAssertion(status_code=200, schema_shape=defs_only_schema)
    assert "no meaningful validation content" in str(excinfo.value) or "schema_shape" in str(
        excinfo.value
    )


def test_defs_referenced_from_items_still_allowed():
    """Verify a schema that legitimately uses '$defs' (referenced from 'items') is
    still accepted -- only truly-unused $defs blocks are rejected.
    """
    valid_schema = {
        "type": "array",
        "$defs": {"Integer": {"type": "integer", "format": "int64"}},
        "items": {"$ref": "#/$defs/Integer"},
    }
    assertion = ResponseAssertion(status_code=200, schema_shape=valid_schema)
    # Accepted, with the OpenAPI-only "int64" format stripped from the $defs entry.
    assert assertion.schema_shape == {
        "type": "array",
        "$defs": {"Integer": {"type": "integer"}},
        "items": {"$ref": "#/$defs/Integer"},
    }


def test_schema_with_definitions_and_ref_allowed():
    """Verify that a schema with internal definitions and $ref is accepted."""
    schema_with_defs = {
        "type": "object",
        "definitions": {
            "Pet": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
            }
        },
        "properties": {
            "pet": {"$ref": "#/definitions/Pet"},
        },
    }
    assertion = ResponseAssertion(status_code=200, schema_shape=schema_with_defs)
    assert assertion.schema_shape == schema_with_defs


def _create_dummy_chunk(op_id: str = "listPets") -> OperationChunk:
    return OperationChunk(
        operation={
            "operationId": op_id,
            "summary": "List pets",
            "responses": {"200": {"description": "OK"}},
        },
        components={},
        metadata=ChunkMetadata(
            method="GET",
            path="/pets",
            operationId=op_id,
            tags=["pets"],
        ),
    )


def test_generation_engine_retry_on_schema_error():
    """Verify GenerationEngine retries when first LLM output fails schema validation."""
    engine = GenerationEngine()
    chunk = _create_dummy_chunk("listPets")

    bad_output = {
        "operation_id": "listPets",
        "description": "List pets",
        "request": {"headers": {}, "query_params": {}},
        "response": {
            "status_code": 200,
            "schema_shape": {"$ref": "#/components/schemas/Pet"},  # bare $ref will fail
        },
        "tags": ["pets"],
    }
    good_output = {
        "operation_id": "listPets",
        "description": "List pets",
        "request": {"headers": {}, "query_params": {}},
        "response": {
            "status_code": 200,
            "schema_shape": {
                "type": "array",
                "items": {"type": "object", "properties": {"id": {"type": "integer"}}},
            },
        },
        "tags": ["pets"],
    }

    call_count = 0

    def mock_complete(messages, cache=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return json.dumps(bad_output)
        return json.dumps(good_output)

    with patch.object(engine.gateway, "complete", side_effect=mock_complete):
        test_case = engine.generate_chunk(chunk)
        assert test_case is not None
        assert test_case.operation_id == "listPets"
        assert test_case.response.schema_shape is not None
        assert test_case.response.schema_shape["type"] == "array"
        assert call_count == 2


def test_generation_engine_double_failure_resilience():
    """Verify that if retry fails again, operation error is handled gracefully in batch."""
    engine = GenerationEngine()
    chunk = _create_dummy_chunk("listPets")

    bad_output = {
        "operation_id": "listPets",
        "description": "List pets",
        "request": {"headers": {}, "query_params": {}},
        "response": {
            "status_code": 200,
            "schema_shape": {"type": "not_valid_schema_type"},
        },
        "tags": ["pets"],
    }

    def mock_complete(messages, cache=None):
        return json.dumps(bad_output)

    with patch.object(engine.gateway, "complete", side_effect=mock_complete):
        result = engine.generate_batch([chunk], stream_stdout=False)
        assert result.total == 1
        assert result.failed == 1
        assert result.succeeded == 0
        assert len(result.errors) == 1
        assert "listPets" in result.errors[0][0]


def test_openapi_only_formats_are_stripped_recursively():
    """OpenAPI-only formats (int64, double, ...) are dropped at every schema depth, since
    Postman's Ajv fails the whole assertion on an unknown format."""
    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "sizeInBytes": {"type": "integer", "format": "int64"},
                "rate": {"type": "number", "format": "double"},
                "createdAt": {"type": "string", "format": "date-time"},
            },
            "allOf": [{"properties": {"count": {"type": "integer", "format": "int32"}}}],
        },
    }
    assertion = ResponseAssertion(status_code=200, schema_shape=schema)
    assert assertion.schema_shape is not None
    item = assertion.schema_shape["items"]
    assert item["properties"]["sizeInBytes"] == {"type": "integer"}
    assert item["properties"]["rate"] == {"type": "number"}
    assert item["properties"]["createdAt"] == {"type": "string", "format": "date-time"}
    assert item["allOf"][0]["properties"]["count"] == {"type": "integer"}


def test_property_named_format_is_not_stripped():
    """A property whose *name* is 'format' is data, not the format keyword."""
    schema = {
        "type": "object",
        "properties": {"format": {"type": "string", "enum": ["pdf", "csv"]}},
        "required": ["format"],
    }
    assertion = ResponseAssertion(status_code=200, schema_shape=schema)
    assert assertion.schema_shape == schema
