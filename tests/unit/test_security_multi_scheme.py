"""Unit tests for multi-scheme alternatives, compound security, scopes, and optional security."""

from specprobe.exporter.http_client import generate_http_document
from specprobe.exporter.postman import generate_postman_collection
from specprobe.generator.models import GeneratedTestCase, RequestFixture, ResponseAssertion


def test_multi_scheme_priority_selection_http() -> None:
    """Verify primary scheme selected by priority and alternatives documented in .http comments."""
    tc = GeneratedTestCase(
        operation_id="multiAuthOp",
        description="Operation with alternative auth",
        request=RequestFixture(method="GET", path="/items"),
        response=ResponseAssertion(status_code=200),
        security=[{"basicAuth": []}, {"bearerAuth": []}, {"apiKeyHeader": []}],
        security_schemes={
            "basicAuth": {"type": "http", "scheme": "basic"},
            "bearerAuth": {"type": "http", "scheme": "bearer"},
            "apiKeyHeader": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
        },
    )

    doc = generate_http_document([tc])
    lines = doc.splitlines()

    # Bearer should win by priority
    assert "@bearerAuth = <token>" in lines
    assert "Authorization: Bearer {{bearerAuth}}" in lines

    # Comments document selection and alternatives
    assert "# Security: bearerAuth" in lines
    alt_line = next(line for line in lines if line.startswith("# Alternatives:"))
    assert "basicAuth" in alt_line
    assert "apiKeyHeader" in alt_line


def test_multi_scheme_priority_selection_postman() -> None:
    """Verify primary scheme selected by priority and alternatives appear in Postman description."""
    tc = GeneratedTestCase(
        operation_id="multiAuthOp",
        description="Operation with alternative auth",
        request=RequestFixture(method="GET", path="/items"),
        response=ResponseAssertion(status_code=200),
        security=[{"basicAuth": []}, {"bearerAuth": []}, {"apiKeyHeader": []}],
        security_schemes={
            "basicAuth": {"type": "http", "scheme": "basic"},
            "bearerAuth": {"type": "http", "scheme": "bearer"},
            "apiKeyHeader": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
        },
    )

    col = generate_postman_collection([tc])
    item = col["item"][0]
    desc = item["request"]["description"]

    assert "Security: bearerAuth" in desc
    assert (
        "Alternatives: basicAuth, apiKeyHeader" in desc
        or "Alternatives: apiKeyHeader, basicAuth" in desc
    )

    headers_by_key = {h["key"]: h["value"] for h in item["request"]["header"]}
    assert headers_by_key["Authorization"] == "Bearer {{bearerAuth}}"


def test_oauth2_scopes_documentation_http_and_postman() -> None:
    """Verify OAuth2 scopes are documented in .http comments and Postman description."""
    tc = GeneratedTestCase(
        operation_id="oauthOp",
        description="Operation with OAuth2 scopes",
        request=RequestFixture(method="GET", path="/pets"),
        response=ResponseAssertion(status_code=200),
        security=[{"oauth2Auth": ["read:pets", "write:pets"]}],
        security_schemes={"oauth2Auth": {"type": "oauth2"}},
    )

    # .http export
    doc = generate_http_document([tc])
    assert "# Scopes: read:pets, write:pets" in doc
    assert "Authorization: Bearer {{oauth2Auth}}" in doc

    # Postman export
    col = generate_postman_collection([tc])
    item = col["item"][0]
    assert "Scopes: read:pets, write:pets" in item["request"]["description"]
    headers_by_key = {h["key"]: h["value"] for h in item["request"]["header"]}
    assert headers_by_key["Authorization"] == "Bearer {{oauth2Auth}}"


def test_optional_security_annotation_http_and_postman() -> None:
    """Verify optional security is annotated with (optional) in comments and description."""
    tc = GeneratedTestCase(
        operation_id="optionalAuthOp",
        description="Operation with optional token",
        request=RequestFixture(method="GET", path="/public-or-private"),
        response=ResponseAssertion(status_code=200),
        security=[{"bearerAuth": []}, {}],
        security_schemes={"bearerAuth": {"type": "http", "scheme": "bearer"}},
    )

    # .http export
    doc = generate_http_document([tc])
    assert "# Security: bearerAuth (optional)" in doc

    # Postman export
    col = generate_postman_collection([tc])
    item = col["item"][0]
    assert "Security: bearerAuth (optional)" in item["request"]["description"]


def test_compound_security_multiple_credentials() -> None:
    """Verify compound security requirements generate all credentials across exporters (FR-006)."""
    tc = GeneratedTestCase(
        operation_id="compoundOp",
        description="Operation requiring both API Key and App ID",
        request=RequestFixture(method="POST", path="/secure-transaction"),
        response=ResponseAssertion(status_code=200),
        security=[{"apiKeyHeader": [], "appIdHeader": []}],
        security_schemes={
            "apiKeyHeader": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
            "appIdHeader": {"type": "apiKey", "in": "header", "name": "X-App-Id"},
        },
    )

    # .http export
    doc = generate_http_document([tc])
    assert "@apiKeyHeader = <api_key>" in doc
    assert "@appIdHeader = <api_key>" in doc
    assert "X-API-Key: {{apiKeyHeader}}" in doc
    assert "X-App-Id: {{appIdHeader}}" in doc

    # Postman export
    col = generate_postman_collection([tc])
    var_keys = {v["key"] for v in col["variable"]}
    assert "apiKeyHeader" in var_keys
    assert "appIdHeader" in var_keys

    item = col["item"][0]
    headers_by_key = {h["key"]: h["value"] for h in item["request"]["header"]}
    assert headers_by_key["X-API-Key"] == "{{apiKeyHeader}}"
    assert headers_by_key["X-App-Id"] == "{{appIdHeader}}"
