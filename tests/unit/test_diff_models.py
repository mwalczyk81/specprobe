"""Unit tests for specprobe diff data models and enum validation."""

import pytest
from pydantic import ValidationError

from specprobe.diff.models import ChangeType, DiffChangeRecord, DiffSummary


def test_change_type_values() -> None:
    """Verify all expected ChangeType enum members exist with correct string representations."""
    assert ChangeType.OPERATION_ADDED == "operation_added"
    assert ChangeType.OPERATION_REMOVED == "operation_removed"
    assert ChangeType.REQUIRED_REQUEST_PROPERTY_ADDED == "required_request_property_added"
    assert ChangeType.RESPONSE_PROPERTY_REMOVED == "response_property_removed"
    assert ChangeType.RESPONSE_STATUS_REMOVED == "response_status_removed"
    assert ChangeType.TYPE_CHANGED == "type_changed"
    assert ChangeType.ENUM_VALUE_REMOVED == "enum_value_removed"


def test_diff_change_record_valid() -> None:
    """Verify DiffChangeRecord instantiates with valid parameters and serializes cleanly."""
    record = DiffChangeRecord(
        change_type=ChangeType.OPERATION_ADDED,
        breaking=False,
        method="POST",
        path="/api/v1/pets",
        location="paths['/api/v1/pets'].post",
        description="Operation 'POST /api/v1/pets' was added in the new specification.",
        old_value=None,
        new_value={"summary": "Create pet"},
    )
    assert record.change_type == ChangeType.OPERATION_ADDED
    assert not record.breaking
    assert record.method == "POST"
    assert record.path == "/api/v1/pets"
    assert record.location == "paths['/api/v1/pets'].post"
    assert record.old_value is None
    assert record.new_value == {"summary": "Create pet"}

    serialized = record.model_dump(mode="json")
    assert serialized["change_type"] == "operation_added"
    assert serialized["breaking"] is False


def test_diff_change_record_extra_field_forbidden() -> None:
    """Verify DiffChangeRecord forbids extra fields per ConfigDict(extra='forbid')."""
    with pytest.raises(ValidationError):
        DiffChangeRecord(  # type: ignore[call-arg]
            change_type=ChangeType.OPERATION_REMOVED,
            breaking=True,
            location="test",
            description="test description",
            unexpected_field="disallowed",
        )


def test_diff_summary_defaults_and_property() -> None:
    """Verify DiffSummary defaults, property calculation, and updates."""
    summary = DiffSummary()
    assert summary.total_changes == 0
    assert summary.breaking_changes == 0
    assert summary.operations_added == 0
    assert summary.operations_removed == 0
    assert summary.schema_breaking_changes == 0
    assert summary.has_breaking_changes is False

    summary.total_changes = 2
    summary.breaking_changes = 1
    summary.operations_added = 1
    summary.operations_removed = 1
    assert summary.has_breaking_changes is True
