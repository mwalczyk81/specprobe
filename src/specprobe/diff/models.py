"""Domain models and Pydantic schemas for OpenAPI structural diffs."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChangeType(StrEnum):
    """Categorization of detected structural differences between OpenAPI specifications."""

    OPERATION_ADDED = "operation_added"
    OPERATION_REMOVED = "operation_removed"
    REQUIRED_REQUEST_PROPERTY_ADDED = "required_request_property_added"
    RESPONSE_PROPERTY_REMOVED = "response_property_removed"
    RESPONSE_STATUS_REMOVED = "response_status_removed"
    TYPE_CHANGED = "type_changed"
    ENUM_VALUE_REMOVED = "enum_value_removed"


class DiffChangeRecord(BaseModel):
    """An individual change detected between two OpenAPI specification versions."""

    model_config = ConfigDict(extra="forbid")

    change_type: ChangeType = Field(
        description="The category of structural change detected",
    )
    breaking: bool = Field(
        description="True if this change is breaking for API consumers, False otherwise",
    )
    method: str | None = Field(
        default=None,
        description=(
            "Uppercase HTTP method of the affected operation (e.g. GET, POST), "
            "or None for spec-level changes"
        ),
    )
    path: str | None = Field(
        default=None,
        description="URL path template of the affected operation (e.g. /pets/{id})",
    )
    location: str = Field(
        description=(
            "Structural locator or pointer where the change occurred "
            "(e.g. responses['200'] or "
            "requestBody.content['application/json'].schema.properties.name)"
        ),
    )
    description: str = Field(
        description="Human-readable explanation of what changed and its contract impact",
    )
    old_value: Any = Field(
        default=None,
        description=("The value or declaration present in baseline specification (null if added)"),
    )
    new_value: Any = Field(
        default=None,
        description=(
            "The value or declaration present in candidate specification (null if removed)"
        ),
    )


class DiffSummary(BaseModel):
    """Summary statistics for changes detected across two specifications."""

    model_config = ConfigDict(extra="forbid")

    total_changes: int = Field(
        default=0,
        description="Total count of all detected change records",
    )
    breaking_changes: int = Field(
        default=0,
        description="Count of changes with breaking=True",
    )
    operations_added: int = Field(
        default=0,
        description="Count of newly added operations (breaking=False)",
    )
    operations_removed: int = Field(
        default=0,
        description="Count of discontinued operations (breaking=True)",
    )
    schema_breaking_changes: int = Field(
        default=0,
        description=(
            "Count of breaking schema and response modifications across shared operations"
        ),
    )

    @property
    def has_breaking_changes(self) -> bool:
        """Return True if any breaking changes were detected."""
        return self.breaking_changes > 0
