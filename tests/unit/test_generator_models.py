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


def test_test_type_defaults_to_positive() -> None:
    """GeneratedTestCase must default test_type to 'positive'."""
    test_case = GeneratedTestCase(
        operation_id="testOp",
        description="Default test type",
        request=RequestFixture(),
        response=ResponseAssertion(status_code=200),
    )
    assert test_case.test_type == "positive"


@pytest.mark.parametrize(
    "valid_type",
    ["positive", "negative_auth_missing", "negative_auth_invalid"],
)
def test_valid_test_types_accepted(valid_type: str) -> None:
    """All defined test_type values must be accepted."""
    test_case = GeneratedTestCase(
        test_type=valid_type,
        operation_id="testOp",
        description=f"Test type {valid_type}",
        request=RequestFixture(),
        response=ResponseAssertion(status_code=200),
    )
    assert test_case.test_type == valid_type


def test_invalid_test_type_rejected() -> None:
    """Unknown test_type values must raise ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        GeneratedTestCase(
            test_type="unknown_variant",
            operation_id="testOp",
            description="Invalid test type",
            request=RequestFixture(),
            response=ResponseAssertion(status_code=200),
        )
    errors = exc_info.value.errors()
    assert any(err["loc"] == ("test_type",) for err in errors)
