"""Unit tests for generator Pydantic data models."""

import pytest
from pydantic import ValidationError

from specprobe.generator.models import GeneratedTestCase, RequestFixture, ResponseAssertion


def test_valid_generated_test_case_instantiation() -> None:
    """Verify that a properly constructed test case passes validation."""
    test_case = GeneratedTestCase(
        operation_id="getPetById",
        description="Fetch a pet by integer id",
        request=RequestFixture(
            path_params={"petId": 42},
            query_params={},
            headers={"Accept": "application/json"},
            body=None,
        ),
        response=ResponseAssertion(
            status_code=200,
            headers={"Content-Type": "application/json"},
            schema_shape={"type": "object", "properties": ["id", "name"]},
        ),
        tags=["pets"],
    )

    assert test_case.operation_id == "getPetById"
    assert test_case.request.path_params == {"petId": 42}
    assert test_case.response.status_code == 200
    assert test_case.tags == ["pets"]


def test_generated_test_case_json_serialization() -> None:
    """Verify serialization and deserialization via model_validate_json."""
    raw_json = (
        '{"operation_id": "createPet", "description": "Create a new pet", '
        '"request": {"body": {"name": "Fido", "tag": "dog"}}, '
        '"response": {"status_code": 201}, "tags": ["pets"]}'
    )
    test_case = GeneratedTestCase.model_validate_json(raw_json)
    assert test_case.operation_id == "createPet"
    assert test_case.request.body == {"name": "Fido", "tag": "dog"}
    assert test_case.request.path_params == {}
    assert test_case.request.query_params == {}
    assert test_case.response.status_code == 201


def test_empty_operation_id_fails_validation() -> None:
    """Empty operation_id must fail validation per min_length=1 constraint."""
    with pytest.raises(ValidationError) as exc_info:
        GeneratedTestCase(
            operation_id="",
            description="Empty op id test",
            request=RequestFixture(),
            response=ResponseAssertion(status_code=200),
        )
    errors = exc_info.value.errors()
    assert any(err["loc"] == ("operation_id",) for err in errors)


def test_invalid_status_code_fails_validation() -> None:
    """Status code out of 100-599 range must fail validation."""
    with pytest.raises(ValidationError) as exc_info:
        ResponseAssertion(status_code=99)
    errors = exc_info.value.errors()
    assert any(err["loc"] == ("status_code",) for err in errors)

    with pytest.raises(ValidationError) as exc_info:
        ResponseAssertion(status_code=600)
    errors = exc_info.value.errors()
    assert any(err["loc"] == ("status_code",) for err in errors)
