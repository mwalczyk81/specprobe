"""Unit tests for VS Code REST Client (.http) export with security scheme variable
parameterization.
"""

from specprobe.exporter.http_client import generate_http_document
from specprobe.generator.models import GeneratedTestCase, RequestFixture, ResponseAssertion


def test_http_bearer_token_variable() -> None:
    """Verify HTTP Bearer auth is declared as file variable and referenced in request block."""
    tc = GeneratedTestCase(
        operation_id="getSecurePet",
        description="Retrieve pet with token",
        request=RequestFixture(
            method="GET",
            path="/pets/1",
            path_params={},
            query_params={},
            headers={"Authorization": "Bearer <token>"},
        ),
        response=ResponseAssertion(status_code=200),
        security=[{"bearerAuth": []}],
        security_schemes={"bearerAuth": {"type": "http", "scheme": "bearer"}},
    )

    doc = generate_http_document([tc])
    lines = doc.splitlines()

    # 1. Top-level file variables
    assert "@baseUrl = http://localhost:8000" in lines
    assert "@bearerAuth = <token>" in lines

    # 2. Request block headers
    assert "Authorization: Bearer {{bearerAuth}}" in lines


def test_http_api_key_header_variable() -> None:
    """Verify API key in header is declared as file variable and referenced in request header."""
    tc = GeneratedTestCase(
        operation_id="createPet",
        description="Create pet with header key",
        request=RequestFixture(
            method="POST",
            path="/pets",
            path_params={},
            query_params={},
            headers={"X-API-Key": "<api_key>"},
        ),
        response=ResponseAssertion(status_code=201),
        security=[{"apiKeyHeaderAuth": []}],
        security_schemes={
            "apiKeyHeaderAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
            }
        },
    )

    doc = generate_http_document([tc])
    lines = doc.splitlines()

    assert "@apiKeyHeaderAuth = <api_key>" in lines
    assert "X-API-Key: {{apiKeyHeaderAuth}}" in lines


def test_http_api_key_query_variable() -> None:
    """Verify API key in query is declared as file variable and referenced in request line URL."""
    tc = GeneratedTestCase(
        operation_id="listPets",
        description="List pets with query key",
        request=RequestFixture(
            method="GET",
            path="/pets",
            path_params={},
            query_params={"api_key": "<api_key>", "limit": 10},
        ),
        response=ResponseAssertion(status_code=200),
        security=[{"apiKeyQueryAuth": []}],
        security_schemes={
            "apiKeyQueryAuth": {
                "type": "apiKey",
                "in": "query",
                "name": "api_key",
            }
        },
    )

    doc = generate_http_document([tc])
    lines = doc.splitlines()

    assert "@apiKeyQueryAuth = <api_key>" in lines
    # Request line contains api_key={{apiKeyQueryAuth}}
    req_line = next(line for line in lines if line.startswith("GET {{baseUrl}}/pets"))
    assert "api_key={{apiKeyQueryAuth}}" in req_line


def test_http_deduplicates_file_variables() -> None:
    """Verify file variables are declared once when requests share a scheme (FR-010)."""
    tc1 = GeneratedTestCase(
        operation_id="getPet1",
        description="Get pet 1",
        request=RequestFixture(method="GET", path="/pets/1"),
        response=ResponseAssertion(status_code=200),
        security=[{"bearerAuth": []}],
        security_schemes={"bearerAuth": {"type": "http", "scheme": "bearer"}},
    )
    tc2 = GeneratedTestCase(
        operation_id="getPet2",
        description="Get pet 2",
        request=RequestFixture(method="GET", path="/pets/2"),
        response=ResponseAssertion(status_code=200),
        security=[{"bearerAuth": []}],
        security_schemes={"bearerAuth": {"type": "http", "scheme": "bearer"}},
    )

    doc = generate_http_document([tc1, tc2])
    bearer_lines = [line for line in doc.splitlines() if line.startswith("@bearerAuth =")]
    assert len(bearer_lines) == 1


def test_http_unauthenticated_has_no_security_variables() -> None:
    """Verify operations with no security requirements declare zero auth file variables."""
    tc = GeneratedTestCase(
        operation_id="getPublic",
        description="Public endpoint",
        request=RequestFixture(method="GET", path="/public"),
        response=ResponseAssertion(status_code=200),
        security=[],
    )

    doc = generate_http_document([tc])
    lines = doc.splitlines()
    assert "@baseUrl = http://localhost:8000" in lines
    assert not any(line.startswith("@") and not line.startswith("@baseUrl") for line in lines)
