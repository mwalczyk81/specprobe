"""Unit tests for SecurityResolver and ResolvedCredential in exporter/security.py."""

from specprobe.exporter.security import (
    ResolvedCredential,
    SecurityResolver,
    format_postman_security_desc,
    format_security_comment,
    sanitize_variable_name,
)


def test_sanitize_variable_name() -> None:
    """Verify variable name sanitization for various OpenAPI scheme names."""
    assert sanitize_variable_name("apiKeyAuth") == "apiKeyAuth"
    assert sanitize_variable_name("user-api-key") == "user_api_key"
    assert sanitize_variable_name("auth.token") == "auth_token"
    assert sanitize_variable_name("123key") == "_123key"
    assert sanitize_variable_name("___") == "auth_credential"
    assert sanitize_variable_name("") == "auth_credential"


def test_resolve_empty_security() -> None:
    """Verify empty security requirements or explicit empty list return no credentials."""
    assert SecurityResolver.resolve_credentials([]) == []
    assert SecurityResolver.resolve_credentials([{}]) == []


def test_resolve_bearer_scheme() -> None:
    """Verify HTTP Bearer security scheme resolution."""
    schemes = {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }
    reqs = [{"bearerAuth": []}]

    creds = SecurityResolver.resolve_credentials(reqs, schemes)
    assert len(creds) == 1
    c = creds[0]
    assert c.scheme_name == "bearerAuth"
    assert c.variable_name == "bearerAuth"
    assert c.transport == "header"
    assert c.target_name == "Authorization"
    assert c.wire_value_template == "Bearer {{bearerAuth}}"
    assert c.default_placeholder == "<token>"
    assert not c.is_optional
    assert c.scopes == []


def test_resolve_basic_scheme() -> None:
    """Verify HTTP Basic security scheme resolution."""
    schemes = {
        "basicAuth": {
            "type": "http",
            "scheme": "basic",
        }
    }
    reqs = [{"basicAuth": []}]

    creds = SecurityResolver.resolve_credentials(reqs, schemes)
    assert len(creds) == 1
    c = creds[0]
    assert c.scheme_name == "basicAuth"
    assert c.transport == "header"
    assert c.target_name == "Authorization"
    assert c.wire_value_template == "Basic {{basicAuth}}"
    assert c.default_placeholder == "<credentials>"


def test_resolve_api_key_header_and_query() -> None:
    """Verify API Key in header and in query parameter resolution."""
    schemes = {
        "headerKey": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Custom-Key",
        },
        "queryKey": {
            "type": "apiKey",
            "in": "query",
            "name": "api_token",
        },
    }

    # Header key
    creds_hdr = SecurityResolver.resolve_credentials([{"headerKey": []}], schemes)
    assert len(creds_hdr) == 1
    assert creds_hdr[0].transport == "header"
    assert creds_hdr[0].target_name == "X-Custom-Key"
    assert creds_hdr[0].wire_value_template == "{{headerKey}}"
    assert creds_hdr[0].default_placeholder == "<api_key>"

    # Query key
    creds_qry = SecurityResolver.resolve_credentials([{"queryKey": []}], schemes)
    assert len(creds_qry) == 1
    assert creds_qry[0].transport == "query"
    assert creds_qry[0].target_name == "api_token"
    assert creds_qry[0].wire_value_template == "{{queryKey}}"
    assert creds_qry[0].default_placeholder == "<api_key>"


def test_resolve_oauth2_with_scopes() -> None:
    """Verify OAuth2 scheme resolution preserves requested scopes."""
    schemes = {
        "oauth2Auth": {
            "type": "oauth2",
            "flows": {},
        }
    }
    reqs = [{"oauth2Auth": ["read:pets", "write:pets"]}]

    creds = SecurityResolver.resolve_credentials(reqs, schemes)
    assert len(creds) == 1
    c = creds[0]
    assert c.transport == "header"
    assert c.wire_value_template == "Bearer {{oauth2Auth}}"
    assert c.scopes == ["read:pets", "write:pets"]


def test_resolve_optional_security() -> None:
    """Verify optional security ({}) sets is_optional=True on resolved credential (FR-013)."""
    schemes = {"bearerAuth": {"type": "http", "scheme": "bearer"}}
    reqs = [{"bearerAuth": []}, {}]

    creds = SecurityResolver.resolve_credentials(reqs, schemes)
    assert len(creds) == 1
    assert creds[0].is_optional is True


def test_resolve_alternative_priority() -> None:
    """Verify priority: Bearer > API Key header > API Key query > Basic (FR-005)."""
    schemes = {
        "bearerAuth": {"type": "http", "scheme": "bearer"},
        "apiKeyHeader": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
        "apiKeyQuery": {"type": "apiKey", "in": "query", "name": "api_key"},
        "basicAuth": {"type": "http", "scheme": "basic"},
    }

    # Bearer vs API Key header vs Basic -> Bearer wins
    creds1 = SecurityResolver.resolve_credentials(
        [{"basicAuth": []}, {"apiKeyHeader": []}, {"bearerAuth": []}],
        schemes,
    )
    assert len(creds1) == 1
    assert creds1[0].scheme_name == "bearerAuth"
    assert "basicAuth" in creds1[0].alternatives
    assert "apiKeyHeader" in creds1[0].alternatives

    # API Key query vs API Key header -> Header wins
    creds2 = SecurityResolver.resolve_credentials(
        [{"apiKeyQuery": []}, {"apiKeyHeader": []}],
        schemes,
    )
    assert len(creds2) == 1
    assert creds2[0].scheme_name == "apiKeyHeader"
    assert creds2[0].alternatives == ["apiKeyQuery"]

    # API Key query vs Basic -> Query wins
    creds3 = SecurityResolver.resolve_credentials(
        [{"basicAuth": []}, {"apiKeyQuery": []}],
        schemes,
    )
    assert len(creds3) == 1
    assert creds3[0].scheme_name == "apiKeyQuery"
    assert creds3[0].alternatives == ["basicAuth"]


def test_resolve_compound_requirements() -> None:
    """Verify compound security requirements generate credentials for all schemes (FR-006)."""
    schemes = {
        "apiKeyHeader": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
        "appIdHeader": {"type": "apiKey", "in": "header", "name": "X-App-Id"},
    }
    reqs = [{"apiKeyHeader": [], "appIdHeader": []}]

    creds = SecurityResolver.resolve_credentials(reqs, schemes)
    assert len(creds) == 2
    names = {c.scheme_name for c in creds}
    assert names == {"apiKeyHeader", "appIdHeader"}


def test_resolve_missing_scheme_heuristics() -> None:
    """Verify deterministic fallback heuristics when scheme definitions are missing (FR-011)."""
    # Bearer substring
    creds_bearer = SecurityResolver.resolve_credentials([{"my_jwt_bearer_token": []}])
    assert len(creds_bearer) == 1
    assert creds_bearer[0].wire_value_template == "Bearer {{my_jwt_bearer_token}}"
    assert creds_bearer[0].target_name == "Authorization"

    # Basic substring
    creds_basic = SecurityResolver.resolve_credentials([{"basic_login": []}])
    assert len(creds_basic) == 1
    assert creds_basic[0].wire_value_template == "Basic {{basic_login}}"

    # Generic key fallback
    creds_custom = SecurityResolver.resolve_credentials([{"custom_auth_header": []}])
    assert len(creds_custom) == 1
    assert creds_custom[0].wire_value_template == "{{custom_auth_header}}"
    assert creds_custom[0].target_name == "custom_auth_header"


def test_format_security_comment_and_postman_desc() -> None:
    """Verify formatting helpers for comments and descriptions."""
    cred = ResolvedCredential(
        scheme_name="oauth2Auth",
        variable_name="oauth2Auth",
        transport="header",
        target_name="Authorization",
        wire_value_template="Bearer {{oauth2Auth}}",
        default_placeholder="<token>",
        is_optional=True,
        scopes=["read:pets", "write:pets"],
        alternatives=["apiKeyAuth"],
    )

    comments = format_security_comment(cred)
    assert "# Security: oauth2Auth (optional)" in comments
    assert "# Alternatives: apiKeyAuth" in comments
    assert "# Scopes: read:pets, write:pets" in comments

    desc = format_postman_security_desc(cred)
    assert "Security: oauth2Auth (optional)" in desc
    assert "Alternatives: apiKeyAuth" in desc
    assert "Scopes: read:pets, write:pets" in desc
