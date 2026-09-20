"""Unit tests for Postman and REST Client negative test export serialization.

Covers tasks T008, T009, T014, and T015.
"""

import pytest

from specprobe.exporter.http_client import generate_http_document
from specprobe.exporter.postman import generate_postman_collection
from specprobe.generator.models import GeneratedTestCase, RequestFixture, ResponseAssertion


@pytest.fixture
def petstore_test_suite() -> list[GeneratedTestCase]:
    """Create a suite of 3 test cases for a single secured operation: happy path, 401, 403."""
    sec = [{"bearerAuth": []}]
    sec_schemes = {"bearerAuth": {"type": "http", "scheme": "bearer"}}

    happy = GeneratedTestCase(
        test_type="positive",
        operation_id="findPetById",
        description="Find pet by ID",
        request=RequestFixture(
            method="GET",
            path="/pets/{petId}",
            path_params={"petId": "42"},
            query_params={},
            headers={"Accept": "application/json", "Authorization": "Bearer <token>"},
            body=None,
        ),
        response=ResponseAssertion(
            status_code=200,
            headers={"Content-Type": "application/json"},
            schema_shape=None,
        ),
        tags=["pets"],
        security=sec,
        security_schemes=sec_schemes,
    )

    tc_401 = GeneratedTestCase(
        test_type="negative_auth_missing",
        operation_id="findPetById",
        description="[401] Missing authentication credentials - findPetById",
        request=RequestFixture(
            method="GET",
            path="/pets/{petId}",
            path_params={"petId": "42"},
            query_params={},
            headers={"Accept": "application/json"},
            body=None,
        ),
        response=ResponseAssertion(
            status_code=401,
            headers={},
            schema_shape=None,
        ),
        tags=["pets", "negative", "auth", "401"],
        security=sec,
        security_schemes=sec_schemes,
    )

    tc_403 = GeneratedTestCase(
        test_type="negative_auth_invalid",
        operation_id="findPetById",
        description="[403] Invalid authentication credentials - findPetById",
        request=RequestFixture(
            method="GET",
            path="/pets/{petId}",
            path_params={"petId": "42"},
            query_params={},
            headers={"Accept": "application/json", "Authorization": "Bearer invalid_token"},
            body=None,
        ),
        response=ResponseAssertion(
            status_code=403,
            headers={},
            schema_shape=None,
        ),
        tags=["pets", "negative", "auth", "403"],
        security=sec,
        security_schemes=sec_schemes,
    )

    return [happy, tc_401, tc_403]


# ---------------------------------------------------------------------------
# Postman Negative Export Tests (T008 & T014)
# ---------------------------------------------------------------------------


def test_postman_export_sibling_requests_and_naming(
    petstore_test_suite: list[GeneratedTestCase],
) -> None:
    """Verify Postman collection groups happy path, 401, and 403 as siblings in tag folder."""
    collection = generate_postman_collection(petstore_test_suite)

    assert len(collection["item"]) == 1
    pets_folder = collection["item"][0]
    assert pets_folder["name"] == "pets"

    items = pets_folder["item"]
    assert len(items) == 3

    names = [item["name"] for item in items]
    assert "Find pet by ID" in names
    assert any("[401]" in name for name in names)
    assert any("[403]" in name for name in names)


def test_postman_export_401_omits_credentials_and_asserts_status(
    petstore_test_suite: list[GeneratedTestCase],
) -> None:
    """Verify 401 Postman item omits authorization headers and asserts status 401."""
    collection = generate_postman_collection(petstore_test_suite)
    pets_folder = collection["item"][0]
    item_401 = next(item for item in pets_folder["item"] if "[401]" in item["name"])

    # Verify no Authorization header exists
    headers = {h["key"]: h["value"] for h in item_401["request"]["header"]}
    assert "Authorization" not in headers
    assert headers.get("Accept") == "application/json"

    # Verify script assertion is 401
    script = "".join(item_401["event"][0]["script"]["exec"])
    assert "pm.response.to.have.status(401)" in script


def test_postman_export_403_inline_invalid_literal(
    petstore_test_suite: list[GeneratedTestCase],
) -> None:
    """Verify 403 Postman item has inline invalid literal and asserts status 403."""
    collection = generate_postman_collection(petstore_test_suite)
    pets_folder = collection["item"][0]
    item_403 = next(item for item in pets_folder["item"] if "[403]" in item["name"])

    # Verify Authorization header contains inline literal, NOT collection variable
    headers = {h["key"]: h["value"] for h in item_403["request"]["header"]}
    assert headers["Authorization"] == "Bearer invalid_token"

    # Verify script assertion is 403
    script = "".join(item_403["event"][0]["script"]["exec"])
    assert "pm.response.to.have.status(403)" in script


def test_postman_export_collection_variables_clean(
    petstore_test_suite: list[GeneratedTestCase],
) -> None:
    """Verify collection variables only contain real credentials, not invalid literals."""
    collection = generate_postman_collection(petstore_test_suite)
    var_keys = [v["key"] for v in collection["variable"]]

    assert "baseUrl" in var_keys
    assert "bearerAuth" in var_keys
    # No invalid variables like bearerAuth_invalid
    assert not any("invalid" in k.lower() for k in var_keys)


# ---------------------------------------------------------------------------
# REST Client Negative Export Tests (T009 & T015)
# ---------------------------------------------------------------------------


def test_http_export_name_annotations_and_expected_status(
    petstore_test_suite: list[GeneratedTestCase],
) -> None:
    """Verify .http export emits # @name <op>_401 and # @name <op>_403 blocks."""
    content = generate_http_document(petstore_test_suite)

    assert "# @name findPetById\n" in content
    assert "# @name findPetById_401\n" in content
    assert "# @name findPetById_403\n" in content

    assert "# Expected Status: 200" in content
    assert "# Expected Status: 401" in content
    assert "# Expected Status: 403" in content


def test_http_export_401_omits_credentials(petstore_test_suite: list[GeneratedTestCase]) -> None:
    """Verify 401 request block omits Authorization header."""
    content = generate_http_document(petstore_test_suite)
    blocks = content.split("###")

    block_401 = next(b for b in blocks if "# @name findPetById_401" in b)
    assert "Authorization" not in block_401
    assert "Accept: application/json" in block_401


def test_http_export_403_inline_invalid_literal(
    petstore_test_suite: list[GeneratedTestCase],
) -> None:
    """Verify 403 request block contains inline invalid literal directly on request."""
    content = generate_http_document(petstore_test_suite)
    blocks = content.split("###")

    block_403 = next(b for b in blocks if "# @name findPetById_403" in b)
    assert "Authorization: Bearer invalid_token" in block_403


def test_http_export_file_variables_clean(petstore_test_suite: list[GeneratedTestCase]) -> None:
    """Verify top-level file variables contain only real scheme placeholders."""
    content = generate_http_document(petstore_test_suite)
    top_lines = content.split("###")[0].strip().splitlines()

    assert "@baseUrl = http://localhost:8000" in top_lines
    assert "@bearerAuth = <token>" in top_lines
    assert not any("invalid" in line for line in top_lines)
