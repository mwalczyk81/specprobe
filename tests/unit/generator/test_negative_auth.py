"""Unit tests for negative authentication generation helpers, 401 and 403 synthesis."""

from specprobe.chunker.models import ChunkMetadata, OperationChunk
from specprobe.exporter.security import ResolvedCredential
from specprobe.generator.models import GeneratedTestCase, RequestFixture, ResponseAssertion
from specprobe.generator.negative_auth import (
    generate_401_test_case,
    generate_403_test_case,
    generate_negative_auth_test_cases,
    get_all_security_target_names,
    get_invalid_credential_literal,
    is_secured_operation,
)


def _sample_chunk(
    op_id: str = "getPet",
    security: list[dict[str, list[str]]] | None = None,
    security_schemes: dict | None = None,
) -> OperationChunk:
    """Create a minimal OperationChunk fixture."""
    return OperationChunk(
        metadata=ChunkMetadata(
            path="/pets/{petId}",
            method="GET",
            operationId=op_id,
            security=security or [],
            tags=["pets"],
        ),
        operation={"responses": {}},
        components={"securitySchemes": security_schemes or {}},
    )


def _sample_happy_tc(
    op_id: str = "getPet",
    security: list[dict[str, list[str]]] | None = None,
    security_schemes: dict | None = None,
    headers: dict[str, str] | None = None,
    query_params: dict[str, str | int] | None = None,
) -> GeneratedTestCase:
    """Create a minimal happy-path GeneratedTestCase fixture."""
    return GeneratedTestCase(
        test_type="positive",
        operation_id=op_id,
        description=f"Happy path for {op_id}",
        request=RequestFixture(
            method="GET",
            path="/pets/42",
            path_params={"petId": "42"},
            query_params=query_params or {},
            headers=headers or {"Accept": "application/json"},
            body=None,
        ),
        response=ResponseAssertion(
            status_code=200,
            headers={"Content-Type": "application/json"},
            schema_shape=None,
        ),
        tags=["pets"],
        security=security or [],
        security_schemes=security_schemes or {},
    )


# ---------------------------------------------------------------------------
# Foundational Helpers (T005 & T006)
# ---------------------------------------------------------------------------


def test_is_secured_operation() -> None:
    """Verify is_secured_operation properly handles secured, unsecured, and optional schemes."""
    assert is_secured_operation(None) is False
    assert is_secured_operation([]) is False
    assert is_secured_operation([{}]) is False
    assert is_secured_operation([{"bearerAuth": []}, {}]) is False  # Optional security
    assert is_secured_operation([{"bearerAuth": []}]) is True
    assert is_secured_operation([{"apiKeyAuth": []}, {"basicAuth": []}]) is True
    assert is_secured_operation([{"apiKeyAuth": [], "oauth2Auth": []}]) is True


def test_get_all_security_target_names() -> None:
    """Verify all security header and query parameter names are collected."""
    reqs = [{"apiKeyHeader": []}, {"apiKeyQuery": []}]
    schemes = {
        "apiKeyHeader": {"type": "apiKey", "in": "header", "name": "X-Custom-Key"},
        "apiKeyQuery": {"type": "apiKey", "in": "query", "name": "auth_token"},
    }
    headers, queries = get_all_security_target_names(reqs, schemes)
    assert "x-custom-key" in headers
    assert "auth_token" in queries


def test_get_invalid_credential_literal_bearer() -> None:
    """Bearer credential produces protocol-valid Bearer invalid_token."""
    cred = ResolvedCredential(
        scheme_name="bearerAuth",
        variable_name="bearerAuth",
        transport="header",
        target_name="Authorization",
        wire_value_template="Bearer {{bearerAuth}}",
        default_placeholder="<token>",
    )
    literal = get_invalid_credential_literal(cred)
    assert literal == "Bearer invalid_token"


def test_get_invalid_credential_literal_basic() -> None:
    """Basic credential produces protocol-valid Basic base64."""
    cred = ResolvedCredential(
        scheme_name="basicAuth",
        variable_name="basicAuth",
        transport="header",
        target_name="Authorization",
        wire_value_template="Basic {{basicAuth}}",
        default_placeholder="<credentials>",
    )
    literal = get_invalid_credential_literal(cred)
    assert literal == "Basic aW52YWxpZDppbnZhbGlk"


def test_get_invalid_credential_literal_apikey_header() -> None:
    """Header API key produces invalid_<name>."""
    cred = ResolvedCredential(
        scheme_name="apiKeyAuth",
        variable_name="apiKeyAuth",
        transport="header",
        target_name="X-API-Key",
        wire_value_template="{{apiKeyAuth}}",
        default_placeholder="<api_key>",
    )
    literal = get_invalid_credential_literal(cred)
    assert literal == "invalid_x_api_key"


def test_get_invalid_credential_literal_apikey_query() -> None:
    """Query API key produces invalid_<name>."""
    cred = ResolvedCredential(
        scheme_name="apiKeyQuery",
        variable_name="apiKeyQuery",
        transport="query",
        target_name="api_key",
        wire_value_template="{{apiKeyQuery}}",
        default_placeholder="<api_key>",
    )
    literal = get_invalid_credential_literal(cred)
    assert literal == "invalid_api_key"


# ---------------------------------------------------------------------------
# User Story 1: 401 Missing Credentials Generation (T007 & T010)
# ---------------------------------------------------------------------------


def test_generate_401_test_case_bearer_stripped() -> None:
    """401 test case strips Authorization header and asserts 401."""
    sec = [{"bearerAuth": []}]
    schemes = {"bearerAuth": {"type": "http", "scheme": "bearer"}}
    happy_tc = _sample_happy_tc(
        op_id="listPets",
        security=sec,
        security_schemes=schemes,
        headers={"Accept": "application/json", "Authorization": "Bearer <token>"},
    )
    chunk = _sample_chunk("listPets", security=sec, security_schemes=schemes)

    tc_401 = generate_401_test_case(happy_tc, chunk)

    assert tc_401.test_type == "negative_auth_missing"
    assert tc_401.operation_id == "listPets"
    assert tc_401.response.status_code == 401
    assert "Authorization" not in tc_401.request.headers
    assert tc_401.request.headers["Accept"] == "application/json"
    assert "negative" in tc_401.tags
    assert "auth" in tc_401.tags
    assert "401" in tc_401.tags
    assert tc_401.tags[0] == "pets"  # Preserves primary folder tag


def test_generate_401_test_case_query_param_stripped() -> None:
    """401 test case strips query auth param while preserving functional params."""
    sec = [{"queryKey": []}]
    schemes = {"queryKey": {"type": "apiKey", "in": "query", "name": "api_key"}}
    happy_tc = _sample_happy_tc(
        op_id="filterPets",
        security=sec,
        security_schemes=schemes,
        query_params={"limit": 10, "api_key": "<api_key>"},
    )
    chunk = _sample_chunk("filterPets", security=sec, security_schemes=schemes)

    tc_401 = generate_401_test_case(happy_tc, chunk)

    assert tc_401.test_type == "negative_auth_missing"
    assert tc_401.response.status_code == 401
    assert "api_key" not in tc_401.request.query_params
    assert tc_401.request.query_params["limit"] == 10


# ---------------------------------------------------------------------------
# User Story 2: 403 Invalid Credentials Generation (T013 & T016)
# ---------------------------------------------------------------------------


def test_generate_403_test_case_bearer_corrupted() -> None:
    """403 test case injects Bearer invalid_token."""
    sec = [{"bearerAuth": []}]
    schemes = {"bearerAuth": {"type": "http", "scheme": "bearer"}}
    happy_tc = _sample_happy_tc(
        op_id="createPet",
        security=sec,
        security_schemes=schemes,
        headers={"Content-Type": "application/json", "Authorization": "Bearer <token>"},
    )
    chunk = _sample_chunk("createPet", security=sec, security_schemes=schemes)

    tc_403 = generate_403_test_case(happy_tc, chunk)

    assert tc_403.test_type == "negative_auth_invalid"
    assert tc_403.operation_id == "createPet"
    assert tc_403.response.status_code == 403
    assert tc_403.request.headers["Authorization"] == "Bearer invalid_token"
    assert tc_403.request.headers["Content-Type"] == "application/json"
    assert "403" in tc_403.tags
    assert tc_403.tags[0] == "pets"


def test_generate_403_test_case_multi_scheme_targets_primary() -> None:
    """Multi-alternative operation corrupts primary resolved scheme (Bearer over ApiKey)."""
    sec = [{"apiKeyHeader": []}, {"bearerAuth": []}]
    schemes = {
        "apiKeyHeader": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
        "bearerAuth": {"type": "http", "scheme": "bearer"},
    }
    happy_tc = _sample_happy_tc(
        op_id="multiAuthPet",
        security=sec,
        security_schemes=schemes,
        headers={"Authorization": "Bearer <token>"},
    )
    chunk = _sample_chunk("multiAuthPet", security=sec, security_schemes=schemes)

    tc_403 = generate_403_test_case(happy_tc, chunk)

    assert tc_403.test_type == "negative_auth_invalid"
    assert tc_403.request.headers["Authorization"] == "Bearer invalid_token"


# ---------------------------------------------------------------------------
# User Story 3: Selective Filtering (T019 & T021)
# ---------------------------------------------------------------------------


def test_generate_negative_auth_test_cases_unsecured() -> None:
    """Unsecured operations produce zero negative test cases."""
    happy_tc = _sample_happy_tc(op_id="publicPet", security=[], security_schemes={})
    chunk = _sample_chunk("publicPet", security=[], security_schemes={})

    cases = generate_negative_auth_test_cases(happy_tc, chunk)
    assert cases == []


def test_generate_negative_auth_test_cases_optional_security() -> None:
    """Operations with optional security produce zero negative test cases."""
    sec = [{"bearerAuth": []}, {}]
    schemes = {"bearerAuth": {"type": "http", "scheme": "bearer"}}
    happy_tc = _sample_happy_tc(op_id="optionalPet", security=sec, security_schemes=schemes)
    chunk = _sample_chunk("optionalPet", security=sec, security_schemes=schemes)

    cases = generate_negative_auth_test_cases(happy_tc, chunk)
    assert cases == []


def test_generate_negative_auth_test_cases_secured_produces_401_and_403() -> None:
    """Secured operation produces exactly 2 negative cases: 401 then 403."""
    sec = [{"bearerAuth": []}]
    schemes = {"bearerAuth": {"type": "http", "scheme": "bearer"}}
    happy_tc = _sample_happy_tc(op_id="securePet", security=sec, security_schemes=schemes)
    chunk = _sample_chunk("securePet", security=sec, security_schemes=schemes)

    cases = generate_negative_auth_test_cases(happy_tc, chunk)
    assert len(cases) == 2
    assert cases[0].test_type == "negative_auth_missing"
    assert cases[0].response.status_code == 401
    assert cases[1].test_type == "negative_auth_invalid"
    assert cases[1].response.status_code == 403
