"""Unit tests for Postman and REST Client export of negative input test cases (404 and 400)."""

from typing import Any

from specprobe.exporter.http_client import generate_http_document
from specprobe.exporter.postman import generate_postman_collection
from specprobe.generator.models import GeneratedTestCase, RequestFixture, ResponseAssertion


def _sample_tc(
    test_type: str,
    op_id: str,
    status_code: int,
    description: str,
    path_params: dict[str, Any] | None = None,
    body: Any = None,
) -> GeneratedTestCase:
    """Helper to create a test case fixture with bearer auth."""
    sec = [{"bearerAuth": []}]
    sec_schemes = {"bearerAuth": {"type": "http", "scheme": "bearer"}}
    path = f"/pets/{path_params['petId']}" if path_params and "petId" in path_params else "/pets"
    return GeneratedTestCase(
        test_type=test_type,
        operation_id=op_id,
        description=description,
        request=RequestFixture(
            method="POST" if body is not None else "GET",
            path=path,
            path_params=path_params or {},
            query_params={},
            headers={"Accept": "application/json", "Authorization": "Bearer <token>"},
            body=body,
        ),
        response=ResponseAssertion(
            status_code=status_code,
            headers={"Content-Type": "application/json"},
            schema_shape=None,
        ),
        tags=["pets"],
        security=sec,
        security_schemes=sec_schemes,
    )


# ===========================================================================
# Postman Export Serialization Tests (T013 / T016)
# ===========================================================================


def test_postman_export_negative_input_cases() -> None:
    """Verify Postman collection item names, status assertions, and credential parameterization."""
    tc_404 = _sample_tc(
        test_type="negative_not_found",
        op_id="getPetById",
        status_code=404,
        description="[404] Resource not found - getPetById",
        path_params={"petId": 999999},
    )
    tc_400 = _sample_tc(
        test_type="negative_invalid_input",
        op_id="createPet",
        status_code=400,
        description="[400] Invalid input - createPet",
        body={"tag": "golden"},
    )

    collection = generate_postman_collection([tc_404, tc_400])
    pets_folder = collection["item"][0]
    items = pets_folder["item"]
    assert len(items) == 2

    # 1. Item names prefixed with [404] and [400]
    item_404 = items[0]
    item_400 = items[1]
    assert item_404["name"] == "[404] Resource not found - getPetById"
    assert item_400["name"] == "[400] Invalid input - createPet"

    # 2. Status script assertions
    script_404 = "".join(item_404["event"][0]["script"]["exec"])
    script_400 = "".join(item_400["event"][0]["script"]["exec"])
    assert "pm.response.to.have.status(404)" in script_404
    assert "pm.response.to.have.status(400)" in script_400

    # 3. Security credentials parameterized (Bearer {{bearerAuth}})
    headers_404 = {h["key"]: h["value"] for h in item_404["request"]["header"]}
    headers_400 = {h["key"]: h["value"] for h in item_400["request"]["header"]}
    assert headers_404["Authorization"] == "Bearer {{bearerAuth}}"
    assert headers_400["Authorization"] == "Bearer {{bearerAuth}}"

    # 4. Collection variables register bearerAuth
    var_keys = [v["key"] for v in collection["variable"]]
    assert "bearerAuth" in var_keys


def test_postman_export_positive_case_with_404_or_400_status() -> None:
    """Verify positive test cases expecting 404/400 are not prefixed with negative tags."""
    pos_404 = _sample_tc(
        test_type="positive",
        op_id="probeResourceNotFound",
        status_code=404,
        description="Probe resource lookup",
        path_params={"petId": 1},
    )
    pos_400 = _sample_tc(
        test_type="positive",
        op_id="probeInputValidation",
        status_code=400,
        description="Probe payload validator",
        body={"name": "test"},
    )

    collection = generate_postman_collection([pos_404, pos_400])
    pets_folder = collection["item"][0]
    items = pets_folder["item"]

    # Names must NOT have [404] or [400] prefix
    assert items[0]["name"] == "Probe resource lookup"
    assert not items[0]["name"].startswith("[404]")
    assert items[1]["name"] == "Probe payload validator"
    assert not items[1]["name"].startswith("[400]")

    # Assertions still verify expected status
    script_404 = "".join(items[0]["event"][0]["script"]["exec"])
    script_400 = "".join(items[1]["event"][0]["script"]["exec"])
    assert "pm.response.to.have.status(404)" in script_404
    assert "pm.response.to.have.status(400)" in script_400


# ===========================================================================
# REST Client (.http) Export Serialization Tests (T013 / T017)
# ===========================================================================


def test_http_export_negative_input_cases() -> None:
    """Verify REST Client @name suffixes, Expected Status comments, and file variables."""
    tc_404 = _sample_tc(
        test_type="negative_not_found",
        op_id="getPetById",
        status_code=404,
        description="[404] Resource not found - getPetById",
        path_params={"petId": 999999},
    )
    tc_400 = _sample_tc(
        test_type="negative_invalid_input",
        op_id="createPet",
        status_code=400,
        description="[400] Invalid input - createPet",
        body={"tag": "golden"},
    )

    doc = generate_http_document([tc_404, tc_400])

    # 1. @name suffixes
    assert "# @name getPetById_404" in doc
    assert "# @name createPet_400" in doc

    # 2. Expected Status comments
    assert "# Expected Status: 404" in doc
    assert "# Expected Status: 400" in doc

    # 3. Parameterized Authorization header
    assert "Authorization: Bearer {{bearerAuth}}" in doc

    # 4. Top-level file variables register @bearerAuth
    assert "@bearerAuth = <token>" in doc


def test_http_export_positive_case_with_404_or_400_status() -> None:
    """Verify positive .http export with 404/400 status is not serialized with negative marks."""
    pos_404 = _sample_tc(
        test_type="positive",
        op_id="probeResourceNotFound",
        status_code=404,
        description="Probe resource lookup",
        path_params={"petId": 1},
    )
    pos_400 = _sample_tc(
        test_type="positive",
        op_id="probeInputValidation",
        status_code=400,
        description="Probe payload validator",
        body={"name": "test"},
    )

    doc = generate_http_document([pos_404, pos_400])

    # Names must NOT have negative suffixes
    assert "# @name probeResourceNotFound\n" in doc
    assert "# @name probeResourceNotFound_404" not in doc
    assert "# @name probeInputValidation\n" in doc
    assert "# @name probeInputValidation_400" not in doc

    # Expected Status comments
    assert "# Expected Status: 404" in doc
    assert "# Expected Status: 400" in doc

    # Parameterized header
    assert "Authorization: Bearer {{bearerAuth}}" in doc
    assert "@bearerAuth = <token>" in doc
