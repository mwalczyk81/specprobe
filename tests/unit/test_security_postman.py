"""Unit tests for Postman Collection export with security scheme variable
parameterization.
"""

from specprobe.exporter.postman import generate_postman_collection
from specprobe.generator.models import GeneratedTestCase, RequestFixture, ResponseAssertion


def test_postman_bearer_token_variable() -> None:
    """Verify HTTP Bearer auth is parameterized as {{<scheme>}} in collection variables."""
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

    col = generate_postman_collection([tc])

    # 1. Collection variables
    vars_by_key = {v["key"]: v for v in col["variable"]}
    assert "baseUrl" in vars_by_key
    assert "bearerAuth" in vars_by_key
    assert vars_by_key["bearerAuth"]["value"] == "<token>"
    assert vars_by_key["bearerAuth"]["type"] == "string"

    # 2. Request item header parameterization
    item = col["item"][0]
    headers_by_key = {h["key"]: h["value"] for h in item["request"]["header"]}
    assert headers_by_key["Authorization"] == "Bearer {{bearerAuth}}"


def test_postman_api_key_header_variable() -> None:
    """Verify API key in header is parameterized in collection variables and request item."""
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

    col = generate_postman_collection([tc])
    vars_by_key = {v["key"]: v for v in col["variable"]}
    assert "apiKeyHeaderAuth" in vars_by_key
    assert vars_by_key["apiKeyHeaderAuth"]["value"] == "<api_key>"

    item = col["item"][0]
    headers_by_key = {h["key"]: h["value"] for h in item["request"]["header"]}
    assert headers_by_key["X-API-Key"] == "{{apiKeyHeaderAuth}}"


def test_postman_api_key_query_variable() -> None:
    """Verify API key in query is parameterized in collection variables and URL query."""
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

    col = generate_postman_collection([tc])
    vars_by_key = {v["key"]: v for v in col["variable"]}
    assert "apiKeyQueryAuth" in vars_by_key
    assert vars_by_key["apiKeyQueryAuth"]["value"] == "<api_key>"

    item = col["item"][0]
    url_obj = item["request"]["url"]
    query_by_key = {q["key"]: q["value"] for q in url_obj.get("query", [])}
    assert query_by_key["api_key"] == "{{apiKeyQueryAuth}}"
    assert "api_key={{apiKeyQueryAuth}}" in url_obj["raw"]


def test_postman_deduplicates_collection_variables() -> None:
    """Verify collection variables are deduplicated when requests share a scheme (FR-010)."""
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

    col = generate_postman_collection([tc1, tc2])
    bearer_vars = [v for v in col["variable"] if v["key"] == "bearerAuth"]
    assert len(bearer_vars) == 1


def test_postman_unauthenticated_has_no_security_variables() -> None:
    """Verify operations with no security requirements declare zero auth variables."""
    tc = GeneratedTestCase(
        operation_id="getPublic",
        description="Public endpoint",
        request=RequestFixture(method="GET", path="/public"),
        response=ResponseAssertion(status_code=200),
        security=[],
    )

    col = generate_postman_collection([tc])
    assert len(col["variable"]) == 1
    assert col["variable"][0]["key"] == "baseUrl"
