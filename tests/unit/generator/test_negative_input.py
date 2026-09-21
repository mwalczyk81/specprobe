"""Unit tests for negative input and resource test generation (404 and 400)."""

from typing import Any
from unittest.mock import MagicMock

from specprobe.chunker.models import ChunkMetadata, OperationChunk
from specprobe.generator.engine import GenerationEngine
from specprobe.generator.models import GeneratedTestCase, RequestFixture, ResponseAssertion
from specprobe.generator.negative_input import (
    PathParameterMutator,
    RequestBodyMutator,
    generate_400_test_case,
    generate_404_test_case,
    generate_negative_input_test_cases,
)


def _make_chunk(
    path: str = "/pets/{petId}",
    method: str = "GET",
    op_id: str = "getPet",
    parameters: list[dict[str, Any]] | None = None,
    request_body: dict[str, Any] | None = None,
    responses: dict[str, Any] | None = None,
    components: dict[str, Any] | None = None,
    security: list[dict[str, list[str]]] | None = None,
) -> OperationChunk:
    """Helper to build an OperationChunk fixture for testing."""
    operation_dict: dict[str, Any] = {
        "operationId": op_id,
        "parameters": parameters or [],
        "responses": responses or {},
    }
    if request_body is not None:
        operation_dict["requestBody"] = request_body

    return OperationChunk(
        metadata=ChunkMetadata(
            path=path,
            method=method,
            operationId=op_id,
            security=security or [],
            tags=["pets"],
        ),
        operation=operation_dict,
        components=components or {},
    )


def _make_happy_tc(
    op_id: str = "getPet",
    path: str = "/pets/123",
    path_params: dict[str, Any] | None = None,
    query_params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    body: Any = None,
    security: list[dict[str, list[str]]] | None = None,
    security_schemes: dict[str, Any] | None = None,
) -> GeneratedTestCase:
    """Helper to build a happy-path GeneratedTestCase fixture for testing."""
    return GeneratedTestCase(
        test_type="positive",
        operation_id=op_id,
        description=f"Happy path test for {op_id}",
        request=RequestFixture(
            method="GET",
            path=path,
            path_params=path_params if path_params is not None else {"petId": 123},
            query_params=query_params or {},
            headers=headers or {"Authorization": "Bearer <token>", "Accept": "application/json"},
            body=body,
        ),
        response=ResponseAssertion(
            status_code=200,
            headers={"Content-Type": "application/json"},
            schema_shape=None,
        ),
        tags=["pets"],
        security=security or [{"bearerAuth": []}],
        security_schemes=security_schemes or {"bearerAuth": {"type": "http", "scheme": "bearer"}},
    )


# ===========================================================================
# User Story 1: 404 Not Found & PathParameterMutator Tests (T005)
# ===========================================================================


def test_path_parameter_mutator_sentinels() -> None:
    """Verify sentinel values for integer, number, uuid, enum, and string schemas."""
    # Integer
    assert (
        PathParameterMutator.get_nonexistent_sentinel({"schema": {"type": "integer"}})
        == PathParameterMutator.SENTINEL_INTEGER
    )
    # Number
    assert PathParameterMutator.get_nonexistent_sentinel({"schema": {"type": "number"}}) == 999999
    # UUID format
    assert (
        PathParameterMutator.get_nonexistent_sentinel(
            {"schema": {"type": "string", "format": "uuid"}}
        )
        == PathParameterMutator.SENTINEL_NIL_UUID
    )
    assert (
        PathParameterMutator.get_nonexistent_sentinel({"format": "uuid"})
        == "00000000-0000-0000-0000-000000000000"
    )
    # Enum
    assert (
        PathParameterMutator.get_nonexistent_sentinel(
            {"schema": {"type": "string", "enum": ["cat", "dog"]}}
        )
        == PathParameterMutator.SENTINEL_STRING_SLUG
    )
    # General string
    assert (
        PathParameterMutator.get_nonexistent_sentinel({"schema": {"type": "string"}})
        == "specprobe-nonexistent-id"
    )
    # Unspecified type defaults to slug
    assert PathParameterMutator.get_nonexistent_sentinel({}) == "specprobe-nonexistent-id"


def test_path_parameter_mutator_leaf_only() -> None:
    """For multi-parameter routes, only the leaf parameter should be mutated."""
    route = "/orgs/{orgId}/teams/{teamId}/members/{memberId}"
    params_def = [
        {"name": "orgId", "in": "path", "schema": {"type": "string"}},
        {"name": "teamId", "in": "path", "schema": {"type": "integer"}},
        {"name": "memberId", "in": "path", "schema": {"type": "string", "format": "uuid"}},
    ]

    leaf = PathParameterMutator.find_leaf_path_parameter(route, params_def)
    assert leaf is not None
    leaf_name, leaf_def = leaf
    assert leaf_name == "memberId"
    assert leaf_def.get("schema", {}).get("format") == "uuid"

    current = {"orgId": "acme", "teamId": 42, "memberId": "12345678-1234-1234-1234-123456789abc"}
    mutated = PathParameterMutator.mutate_path_params(route, current, params_def)
    assert mutated is not None
    # Leaf mutated to nil UUID
    assert mutated["memberId"] == "00000000-0000-0000-0000-000000000000"
    # Ancestor parameters preserved
    assert mutated["orgId"] == "acme"
    assert mutated["teamId"] == 42


def test_path_parameter_mutator_no_path_params() -> None:
    """Routes without path parameters should return None."""
    assert PathParameterMutator.find_leaf_path_parameter("/pets", []) is None
    assert PathParameterMutator.mutate_path_params("/pets", {}, []) is None


def test_generate_404_test_case_success() -> None:
    """Verify generate_404_test_case constructs a valid 404 test case preserving state."""
    chunk = _make_chunk(
        path="/pets/{petId}",
        parameters=[{"name": "petId", "in": "path", "schema": {"type": "integer"}}],
        responses={
            "404": {
                "description": "Pet not found",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"message": {"type": "string"}},
                        }
                    }
                },
            }
        },
    )
    happy_tc = _make_happy_tc(
        op_id="getPetById",
        path="/pets/42",
        path_params={"petId": 42},
        headers={"Authorization": "Bearer <token>", "X-Custom": "123"},
    )

    tc_404 = generate_404_test_case(happy_tc, chunk)
    assert tc_404 is not None
    assert tc_404.test_type == "negative_not_found"
    assert tc_404.operation_id == "getPetById"
    assert tc_404.description == "[404] Resource not found - getPetById"
    assert tc_404.response.status_code == 404
    assert tc_404.response.schema_shape == {
        "type": "object",
        "properties": {"message": {"type": "string"}},
    }
    # Path params mutated
    assert tc_404.request.path_params == {"petId": 999999}
    # Headers and credentials retained
    assert tc_404.request.headers["Authorization"] == "Bearer <token>"
    assert tc_404.request.headers["X-Custom"] == "123"
    # Tags
    assert "pets" in tc_404.tags
    assert "negative" in tc_404.tags
    assert "404" in tc_404.tags
    assert "not_found" in tc_404.tags
    # Security metadata retained
    assert tc_404.security == happy_tc.security
    assert tc_404.security_schemes == happy_tc.security_schemes


def test_generate_404_test_case_skipped_when_no_path_params() -> None:
    """Operations with no path parameters should return None."""
    chunk = _make_chunk(path="/pets", parameters=[])
    happy_tc = _make_happy_tc(op_id="listPets", path_params={})

    assert generate_404_test_case(happy_tc, chunk) is None


# ===========================================================================
# User Story 2: 400 Bad Request & RequestBodyMutator Tests (T009)
# ===========================================================================


def test_request_body_mutator_extract_json_schema() -> None:
    """Verify get_json_schema extracts application/json and application/*+json schemas."""
    # Standard application/json
    chunk1 = _make_chunk(
        request_body={
            "content": {
                "application/json": {
                    "schema": {"type": "object", "properties": {"name": {"type": "string"}}}
                }
            }
        }
    )
    schema1 = RequestBodyMutator.get_json_schema(chunk1)
    assert schema1 is not None
    assert schema1["type"] == "object"

    # Custom +json media type
    chunk2 = _make_chunk(
        request_body={
            "content": {
                "application/merge-patch+json": {
                    "schema": {"type": "object", "properties": {"age": {"type": "integer"}}}
                }
            }
        }
    )
    schema2 = RequestBodyMutator.get_json_schema(chunk2)
    assert schema2 is not None
    assert "age" in schema2["properties"]

    # Non-JSON media type returns None
    chunk3 = _make_chunk(
        request_body={
            "content": {
                "multipart/form-data": {
                    "schema": {"type": "object", "properties": {"file": {"type": "string"}}}
                }
            }
        }
    )
    assert RequestBodyMutator.get_json_schema(chunk3) is None

    # Unconstrained schema returns None
    chunk4 = _make_chunk(request_body={"content": {"application/json": {"schema": {}}}})
    assert RequestBodyMutator.get_json_schema(chunk4) is None


def test_request_body_mutator_resolve_ref() -> None:
    """Verify get_json_schema resolves local components.schemas $ref pointer."""
    chunk = _make_chunk(
        request_body={
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Pet"}}}
        },
        components={
            "schemas": {
                "Pet": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {"name": {"type": "string"}},
                }
            }
        },
    )
    schema = RequestBodyMutator.get_json_schema(chunk)
    assert schema is not None
    assert schema["required"] == ["name"]


def test_request_body_mutator_omit_required_field() -> None:
    """Verify first declared required field in schema order is omitted."""
    schema = {
        "type": "object",
        "required": ["name", "category"],
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
            "category": {"type": "string"},
        },
    }
    body = {"id": 1, "name": "Fluffy", "category": "dog"}
    mutated = RequestBodyMutator.mutate_json_body(body, schema)
    assert mutated is not None
    # 'name' is the first required field, so it must be removed
    assert "name" not in mutated
    assert mutated["id"] == 1
    assert mutated["category"] == "dog"


def test_request_body_mutator_type_inversion() -> None:
    """When no required fields are declared, invert the first property type."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
    }
    body = {"name": "Fluffy", "age": 3}
    mutated = RequestBodyMutator.mutate_json_body(body, schema)
    assert mutated is not None
    # 'name' is string, inverted to array
    assert mutated["name"] == ["__specprobe_invalid_type__"]
    assert mutated["age"] == 3


def test_request_body_mutator_array_type_inversion() -> None:
    """Root array schema replaced with empty dict."""
    schema = {"type": "array", "items": {"type": "string"}}
    body = ["tag1", "tag2"]
    mutated = RequestBodyMutator.mutate_json_body(body, schema)
    assert mutated == {}


def test_generate_400_test_case_success() -> None:
    """Verify generate_400_test_case constructs a valid 400 test case."""
    chunk = _make_chunk(
        method="POST",
        op_id="createPet",
        path="/pets",
        request_body={
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["name"],
                        "properties": {"name": {"type": "string"}, "tag": {"type": "string"}},
                    }
                }
            }
        },
    )
    happy_tc = _make_happy_tc(
        op_id="createPet",
        path="/pets",
        path_params={},
        body={"name": "Buddy", "tag": "golden"},
    )

    tc_400 = generate_400_test_case(happy_tc, chunk)
    assert tc_400 is not None
    assert tc_400.test_type == "negative_invalid_input"
    assert tc_400.operation_id == "createPet"
    assert tc_400.description == "[400] Invalid input - createPet"
    assert tc_400.response.status_code == 400
    # Required 'name' omitted
    assert tc_400.request.body == {"tag": "golden"}
    # Credentials retained
    assert tc_400.request.headers["Authorization"] == "Bearer <token>"
    # Tags
    assert "negative" in tc_400.tags
    assert "400" in tc_400.tags
    assert "invalid_input" in tc_400.tags


def test_generate_400_test_case_skipped_when_bodiless() -> None:
    """Bodiless operations must return None."""
    chunk = _make_chunk(method="GET", op_id="getPet")
    happy_tc = _make_happy_tc(op_id="getPet", body=None)

    assert generate_400_test_case(happy_tc, chunk) is None


def test_generate_negative_input_test_cases_ordering() -> None:
    """Verify deterministic multiple sibling ordering: 404 first, then 400."""
    chunk = _make_chunk(
        method="PUT",
        op_id="updatePet",
        path="/pets/{petId}",
        parameters=[{"name": "petId", "in": "path", "schema": {"type": "integer"}}],
        request_body={
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["name"],
                        "properties": {"name": {"type": "string"}},
                    }
                }
            }
        },
    )
    happy_tc = _make_happy_tc(
        op_id="updatePet",
        path="/pets/42",
        path_params={"petId": 42},
        body={"name": "Rocky"},
    )

    cases = generate_negative_input_test_cases(happy_tc, chunk, not_found=True, invalid_input=True)
    assert len(cases) == 2
    assert cases[0].test_type == "negative_not_found"
    assert cases[0].response.status_code == 404
    assert cases[1].test_type == "negative_invalid_input"
    assert cases[1].response.status_code == 400

    # Test independent flag control
    cases_no_404 = generate_negative_input_test_cases(
        happy_tc, chunk, not_found=False, invalid_input=True
    )
    assert len(cases_no_404) == 1
    assert cases_no_404[0].test_type == "negative_invalid_input"

    cases_no_400 = generate_negative_input_test_cases(
        happy_tc, chunk, not_found=True, invalid_input=False
    )
    assert len(cases_no_400) == 1
    assert cases_no_400[0].test_type == "negative_not_found"


def test_generation_engine_batch_negative_input_integration() -> None:
    """Verify GenerationEngine.generate_batch generates negative input siblings in exact order:
    positive -> 401 -> 403 -> 404 -> 400.
    """
    chunk = _make_chunk(
        method="PUT",
        op_id="updatePet",
        path="/pets/{petId}",
        parameters=[{"name": "petId", "in": "path", "schema": {"type": "integer"}}],
        request_body={
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["name"],
                        "properties": {"name": {"type": "string"}},
                    }
                }
            }
        },
        security=[{"bearerAuth": []}],
        components={"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
    )
    happy_tc = _make_happy_tc(
        op_id="updatePet",
        path="/pets/42",
        path_params={"petId": 42},
        body={"name": "Rocky"},
        security=[{"bearerAuth": []}],
        security_schemes={"bearerAuth": {"type": "http", "scheme": "bearer"}},
    )

    mock_gateway = MagicMock()
    engine = GenerationEngine(gateway=mock_gateway)
    engine.generate_chunk = MagicMock(return_value=happy_tc)

    # 1. All enabled: positive -> 401 -> 403 -> 404 -> 400
    res = engine.generate_batch(
        [chunk],
        stream_stdout=False,
        negative_auth=True,
        not_found=True,
        invalid_input=True,
    )
    assert len(res.test_cases) == 5
    assert [tc.test_type for tc in res.test_cases] == [
        "positive",
        "negative_auth_missing",
        "negative_auth_invalid",
        "negative_not_found",
        "negative_invalid_input",
    ]
    assert [tc.response.status_code for tc in res.test_cases] == [200, 401, 403, 404, 400]

    # 2. Disable not_found
    res_no_404 = engine.generate_batch(
        [chunk],
        stream_stdout=False,
        negative_auth=True,
        not_found=False,
        invalid_input=True,
    )
    assert [tc.test_type for tc in res_no_404.test_cases] == [
        "positive",
        "negative_auth_missing",
        "negative_auth_invalid",
        "negative_invalid_input",
    ]

    # 3. Disable invalid_input
    res_no_400 = engine.generate_batch(
        [chunk],
        stream_stdout=False,
        negative_auth=True,
        not_found=True,
        invalid_input=False,
    )
    assert [tc.test_type for tc in res_no_400.test_cases] == [
        "positive",
        "negative_auth_missing",
        "negative_auth_invalid",
        "negative_not_found",
    ]
