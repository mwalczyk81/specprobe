"""Unit tests for VS Code REST Client (.http) serializer."""

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from specprobe.exporter.http_client import (
    generate_http_document,
    generate_rest_client_environments,
)
from specprobe.exporter.models import ExportEnvironment
from specprobe.generator.models import GeneratedTestCase, RequestFixture, ResponseAssertion


@pytest.fixture
def sample_get_test_case() -> GeneratedTestCase:
    """Return a representative GET GeneratedTestCase for testing .http serialization."""
    return GeneratedTestCase(
        operation_id="showPetById",
        description="Retrieve specific pet by ID",
        request=RequestFixture(
            method="GET",
            path="/pets/{petId}",
            path_params={"petId": "42"},
            query_params={},
            headers={"Accept": "application/json"},
            body=None,
        ),
        response=ResponseAssertion(
            status_code=200,
            headers={"Content-Type": "application/json"},
            schema_shape={
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "tag": {"type": "string"},
                },
            },
        ),
        tags=["pets", "store"],
    )


@pytest.fixture
def sample_post_test_case() -> GeneratedTestCase:
    """Return a representative POST GeneratedTestCase with a JSON body."""
    return GeneratedTestCase(
        operation_id="createPet",
        description="Create a new pet in store",
        request=RequestFixture(
            method="POST",
            path="/pets",
            path_params={},
            query_params={},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            body={"name": "Fido", "tag": "dog"},
        ),
        response=ResponseAssertion(
            status_code=201,
            headers={"Content-Type": "application/json"},
            schema_shape={
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                },
            },
        ),
        tags=["pets"],
    )


def test_empty_test_cases() -> None:
    """Verify empty input produces an empty .http document with zero request blocks."""
    doc = generate_http_document([])
    assert doc == ""


def test_base_url_declaration(sample_get_test_case: GeneratedTestCase) -> None:
    """Verify document starts with @baseUrl declaration with default URL."""
    doc = generate_http_document([sample_get_test_case])
    assert doc.startswith("@baseUrl = http://localhost:8000\n\n")


def test_custom_base_url(sample_get_test_case: GeneratedTestCase) -> None:
    """Verify custom base_url parameter is reflected in the top-level declaration."""
    custom_url = "https://api.petstore.example.com/v2"
    doc = generate_http_document([sample_get_test_case], base_url=custom_url)
    assert doc.startswith(f"@baseUrl = {custom_url}\n\n")


def test_single_get_request(sample_get_test_case: GeneratedTestCase) -> None:
    """Verify complete formatting of a GET request block with metadata comments."""
    doc = generate_http_document([sample_get_test_case])

    expected_block = (
        "###\n"
        "# @name showPetById\n"
        "# Operation: showPetById\n"
        "# Description: Retrieve specific pet by ID\n"
        "# Expected Status: 200\n"
        "# Expected Schema: object (properties: id, name, tag)\n"
        "GET {{baseUrl}}/pets/42 HTTP/1.1\n"
        "Accept: application/json"
    )

    assert expected_block in doc


def test_none_schema_shape_omits_schema_comment() -> None:
    """A schema_shape=None must not emit '# Expected Schema:' in .http output."""
    tc = GeneratedTestCase(
        operation_id="getPet",
        description="Get pet by ID",
        request=RequestFixture(
            method="GET",
            path="/pets/1",
            path_params={},
            query_params={},
            headers={"Accept": "application/json"},
            body=None,
        ),
        response=ResponseAssertion(
            status_code=204,
            headers={"Content-Type": "application/json"},
            schema_shape=None,
        ),
        tags=["pets"],
    )
    doc = generate_http_document([tc])

    # Must retain metadata and request line
    assert "# Operation: getPet" in doc
    assert "# Expected Status: 204" in doc
    assert "GET {{baseUrl}}/pets/1 HTTP/1.1" in doc

    # Must NOT emit expected schema
    assert "# Expected Schema:" not in doc
    assert "# Expected Properties:" not in doc


def test_post_request_with_json_body(sample_post_test_case: GeneratedTestCase) -> None:
    """Verify POST request formatting with separated JSON body."""
    doc = generate_http_document([sample_post_test_case])

    assert "POST {{baseUrl}}/pets HTTP/1.1" in doc
    assert "Accept: application/json" in doc
    assert "Content-Type: application/json" in doc

    # Body must be preceded by an empty blank line after headers
    expected_body = '{\n  "name": "Fido",\n  "tag": "dog"\n}'
    assert f"\n\n{expected_body}" in doc


def test_path_parameter_substitution_and_url_encoding() -> None:
    """Verify path parameters with spaces or special characters are URL-encoded."""
    tc = GeneratedTestCase(
        operation_id="findPetsByStatus",
        description="Find pets by special status",
        request=RequestFixture(
            method="GET",
            path="/pets/status/{statusVal}",
            path_params={"statusVal": "sold out/pending"},
            query_params={},
            headers={},
            body=None,
        ),
        response=ResponseAssertion(status_code=200, headers={}, schema_shape=None),
        tags=["pets"],
    )

    doc = generate_http_document([tc])
    # "/" in parameter value should be encoded as %2F
    assert "GET {{baseUrl}}/pets/status/sold%20out%2Fpending HTTP/1.1" in doc


def test_query_params_formatting() -> None:
    """Verify query parameters are appended to the request line URL."""
    tc = GeneratedTestCase(
        operation_id="listPets",
        description="List pets with limit and offset",
        request=RequestFixture(
            method="GET",
            path="/pets",
            path_params={},
            query_params={"limit": 10, "offset": 20},
            headers={"Accept": "application/json"},
            body=None,
        ),
        response=ResponseAssertion(status_code=200, headers={}, schema_shape=None),
        tags=["pets"],
    )

    doc = generate_http_document([tc])
    assert "GET {{baseUrl}}/pets?limit=10&offset=20 HTTP/1.1" in doc


def test_missing_optional_elements() -> None:
    """Verify clean formatting when schema_shape, headers, and body are empty."""
    tc = GeneratedTestCase(
        operation_id="healthCheck",
        description="Check service health",
        request=RequestFixture(
            method="GET",
            path="/healthz",
            path_params={},
            query_params={},
            headers={},
            body=None,
        ),
        response=ResponseAssertion(status_code=200, headers={}, schema_shape=None),
        tags=[],
    )

    doc = generate_http_document([tc])

    assert "# @name healthCheck\n# Operation: healthCheck\n" in doc
    assert "# Description: Check service health\n" in doc
    assert "# Expected Status: 200\n" in doc
    assert "# Expected Properties:" not in doc
    # Request line with no headers or body ends cleanly
    assert "GET {{baseUrl}}/healthz HTTP/1.1\n" in doc


def test_defs_not_listed_as_expected_property() -> None:
    """Verify an unreferenced-looking '$defs' block never leaks into the 'Expected
    Properties' comment (regression: array schema with only $defs+items $ref, no
    'properties' key, previously fell through to the raw-key fallback and printed
    'Expected Properties: $defs').
    """
    tc = GeneratedTestCase(
        operation_id="listPets",
        description="List pets with a limit",
        request=RequestFixture(
            method="GET",
            path="/pets",
            path_params={},
            query_params={"limit": "10"},
            headers={},
            body=None,
        ),
        response=ResponseAssertion(
            status_code=200,
            headers={},
            schema_shape={
                "type": "array",
                "$defs": {"Integer": {"type": "integer", "format": "int64"}},
                "items": {"$ref": "#/$defs/Integer"},
            },
        ),
        tags=["pets"],
    )

    doc = generate_http_document([tc])

    assert "$defs" not in doc
    assert "# Expected Properties:" not in doc
    assert "# Expected Schema: array" in doc


def test_multiple_requests_separation(
    sample_get_test_case: GeneratedTestCase,
    sample_post_test_case: GeneratedTestCase,
) -> None:
    """Verify multiple requests are separated by delimiters and blank lines."""
    doc = generate_http_document([sample_get_test_case, sample_post_test_case])

    assert doc.count("###") == 2
    # Ensure separation between first block and second block delimiter
    assert "\n\n###\n# @name createPet" in doc


# ---------------------------------------------------------------------------
# Hypothesis Property Test for Constitution Principle II Determinism
# ---------------------------------------------------------------------------


@st.composite
def generated_test_case_strategy(draw: Any) -> GeneratedTestCase:
    """Hypothesis composite strategy generating arbitrary GeneratedTestCase records."""
    op_id = draw(
        st.text(
            min_size=1,
            max_size=25,
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_",
        )
    )
    description = draw(st.text(min_size=1, max_size=50))
    method = draw(st.sampled_from(["GET", "POST", "PUT", "DELETE", "PATCH"]))
    path = "/" + draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789_/-",
        )
    )
    path_params = draw(
        st.dictionaries(
            keys=st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"),
            values=st.text(min_size=1, max_size=20),
            max_size=2,
        )
    )
    query_params = draw(
        st.dictionaries(
            keys=st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"),
            values=st.one_of(st.integers(min_value=0, max_value=100), st.text(max_size=20)),
            max_size=2,
        )
    )
    headers = draw(
        st.dictionaries(
            keys=st.sampled_from(["Accept", "Content-Type", "Authorization", "X-Custom-Header"]),
            values=st.text(min_size=1, max_size=30),
            max_size=3,
        )
    )
    body = draw(
        st.one_of(
            st.none(),
            st.dictionaries(
                keys=st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"),
                values=st.text(max_size=20),
                max_size=3,
            ),
        )
    )
    test_type = draw(
        st.sampled_from(
            [
                "positive",
                "negative_auth_missing",
                "negative_auth_invalid",
                "negative_not_found",
                "negative_invalid_input",
            ]
        )
    )
    if test_type == "negative_auth_missing":
        status_code = 401
    elif test_type == "negative_auth_invalid":
        status_code = 403
    elif test_type == "negative_not_found":
        status_code = 404
    elif test_type == "negative_invalid_input":
        status_code = 400
    else:
        status_code = draw(st.integers(min_value=200, max_value=299))
    resp_headers = draw(
        st.dictionaries(
            keys=st.sampled_from(["Content-Type", "ETag", "Location"]),
            values=st.text(min_size=1, max_size=20),
            max_size=2,
        )
    )
    schema_shape = draw(
        st.one_of(
            st.none(),
            st.fixed_dictionaries(
                {
                    "type": st.just("object"),
                    "properties": st.dictionaries(
                        keys=st.text(
                            min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"
                        ),
                        values=st.fixed_dictionaries({"type": st.just("string")}),
                        max_size=4,
                    ),
                }
            ),
        )
    )
    tags = draw(st.lists(st.text(min_size=1, max_size=15), max_size=3))
    security = draw(
        st.sampled_from(
            [
                [],
                [{"bearerAuth": []}],
                [{"apiKeyAuth": []}],
                [{"bearerAuth": []}, {}],
                [{"oauth2Auth": ["read:pets", "write:pets"]}],
                [{"apiKeyAuth": [], "appIdAuth": []}],
            ]
        )
    )
    security_schemes = draw(
        st.sampled_from(
            [
                {},
                {
                    "bearerAuth": {"type": "http", "scheme": "bearer"},
                    "apiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
                    "oauth2Auth": {"type": "oauth2"},
                    "appIdAuth": {"type": "apiKey", "in": "header", "name": "X-App-Id"},
                },
            ]
        )
    )

    return GeneratedTestCase(
        test_type=test_type,
        operation_id=op_id,
        description=description,
        request=RequestFixture(
            method=method,
            path=path,
            path_params=path_params,
            query_params=query_params,
            headers=headers,
            body=body,
        ),
        response=ResponseAssertion(
            status_code=status_code,
            headers=resp_headers,
            schema_shape=schema_shape,
        ),
        tags=tags,
        security=security,
        security_schemes=security_schemes,
    )


@given(
    test_cases=st.lists(generated_test_case_strategy(), min_size=0, max_size=6),
    base_url=st.sampled_from(
        ["http://localhost:8000", "https://api.example.com", "http://127.0.0.1:5000/v1"]
    ),
)
def test_hypothesis_http_export_determinism(
    test_cases: list[GeneratedTestCase],
    base_url: str,
) -> None:
    """Constitution Principle II property test:
    Assert calling generate_http_document twice on the same input produces
    byte-identical string output across arbitrary test case batches.
    """
    doc1 = generate_http_document(test_cases, base_url=base_url)
    doc2 = generate_http_document(test_cases, base_url=base_url)

    assert doc1 == doc2


def test_generate_rest_client_environments_basic(sample_get_test_case: GeneratedTestCase) -> None:
    """Test generating http-client.env.json structure with multiple environments and credentials."""
    tc_auth = GeneratedTestCase(
        operation_id="secureOp",
        description="Secure operation requiring API key and Bearer token",
        request=RequestFixture(
            method="GET",
            path="/secure",
            path_params={},
            query_params={},
            headers={},
            body=None,
        ),
        response=ResponseAssertion(status_code=200, headers={}, schema_shape=None),
        tags=["auth"],
        security=[{"apiKey": [], "bearerAuth": []}],
        security_schemes={
            "apiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
            "bearerAuth": {"type": "http", "scheme": "bearer"},
        },
    )

    envs = [
        ExportEnvironment(name="local", base_url="http://localhost:8000"),
        ExportEnvironment(name="work", base_url="https://api.work.internal"),
    ]

    result = generate_rest_client_environments(envs, [sample_get_test_case, tc_auth])

    assert "local" in result
    assert "work" in result
    assert result["local"]["baseUrl"] == "http://localhost:8000"
    assert result["work"]["baseUrl"] == "https://api.work.internal"
    # Fallback to default placeholders from SecurityResolver (<api_key>, <token>)
    assert result["local"]["apiKey"] == "<api_key>"
    assert result["local"]["bearerAuth"] == "<token>"
    assert result["work"]["apiKey"] == "<api_key>"
    assert result["work"]["bearerAuth"] == "<token>"


def test_generate_rest_client_environments_custom_vars() -> None:
    """Test that explicit variable mappings on ExportEnvironment take precedence."""
    tc_auth = GeneratedTestCase(
        operation_id="secureOp",
        description="Secure operation",
        request=RequestFixture(
            method="GET",
            path="/secure",
            path_params={},
            query_params={},
            headers={},
            body=None,
        ),
        response=ResponseAssertion(status_code=200, headers={}, schema_shape=None),
        security=[{"apiKey": []}],
        security_schemes={"apiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"}},
    )

    envs = [
        ExportEnvironment(
            name="dev",
            base_url="http://localhost:8000",
            variables={"apiKey": "custom-dev-secret"},
        ),
    ]

    result = generate_rest_client_environments(envs, [tc_auth])
    assert result["dev"]["baseUrl"] == "http://localhost:8000"
    assert result["dev"]["apiKey"] == "custom-dev-secret"


def test_generate_rest_client_environments_skips_negative_auth() -> None:
    """Test that negative authentication test cases do not generate credential variables."""
    tc_neg = GeneratedTestCase(
        test_type="negative_auth_missing",
        operation_id="secureOp",
        description="Negative auth test case",
        request=RequestFixture(
            method="GET",
            path="/secure",
            path_params={},
            query_params={},
            headers={},
            body=None,
        ),
        response=ResponseAssertion(status_code=401, headers={}, schema_shape=None),
        security=[{"apiKey": []}],
        security_schemes={"apiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"}},
    )

    envs = [ExportEnvironment(name="local", base_url="http://localhost:8000")]
    result = generate_rest_client_environments(envs, [tc_neg])
    assert result["local"] == {"baseUrl": "http://localhost:8000"}


def test_generate_http_document_include_env_header_false(
    sample_get_test_case: GeneratedTestCase,
) -> None:
    """Test that setting include_env_header=False omits top-level variable declarations."""
    tc_auth = GeneratedTestCase(
        operation_id="secureOp",
        description="Secure operation",
        request=RequestFixture(
            method="GET",
            path="/secure",
            path_params={},
            query_params={},
            headers={},
            body=None,
        ),
        response=ResponseAssertion(status_code=200, headers={}, schema_shape=None),
        security=[{"apiKey": []}],
        security_schemes={"apiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"}},
    )

    # With include_env_header=False
    doc_no_header = generate_http_document(
        [sample_get_test_case, tc_auth], include_env_header=False
    )
    assert "@baseUrl" not in doc_no_header
    assert "@apiKey" not in doc_no_header
    # But requests still reference {{baseUrl}} and {{apiKey}}
    assert "{{baseUrl}}/pets/42" in doc_no_header
    assert "{{apiKey}}" in doc_no_header
    assert doc_no_header.startswith("###")

    # With include_env_header=True (default)
    doc_with_header = generate_http_document(
        [sample_get_test_case, tc_auth], include_env_header=True
    )
    assert doc_with_header.startswith("@baseUrl = http://localhost:8000")
    assert "@apiKey = <api_key>" in doc_with_header
