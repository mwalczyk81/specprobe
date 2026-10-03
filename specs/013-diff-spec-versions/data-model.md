# Data Models: `specprobe diff`

**Feature Branch**: `013-diff-spec-versions`
**Date**: 2026-10-03
**Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/013-diff-spec-versions/spec.md)

---

## 1. Schema & Change Types

```python
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ChangeType(str, Enum):
    """Categorization of detected structural differences between OpenAPI specifications."""

    OPERATION_ADDED = "operation_added"
    OPERATION_REMOVED = "operation_removed"
    REQUIRED_REQUEST_PROPERTY_ADDED = "required_request_property_added"
    RESPONSE_PROPERTY_REMOVED = "response_property_removed"
    RESPONSE_STATUS_REMOVED = "response_status_removed"
    TYPE_CHANGED = "type_changed"
    ENUM_VALUE_REMOVED = "enum_value_removed"
```

---

## 2. DiffChangeRecord

Represents an individual structural change detected between the baseline and candidate specifications. Emitted as a JSON object on `stdout` during streaming.

```python
class DiffChangeRecord(BaseModel):
    """An individual change detected between two OpenAPI specification versions."""

    model_config = ConfigDict(extra="forbid")

    change_type: ChangeType = Field(description="The category of structural change detected")
    breaking: bool = Field(
        description="True if this change is breaking for API consumers, False otherwise"
    )
    method: str | None = Field(
        default=None,
        description="Uppercase HTTP method of the affected operation (e.g. GET, POST), or None for spec-level changes",
    )
    path: str | None = Field(
        default=None,
        description="URL path template of the affected operation (e.g. /pets/{id})",
    )
    location: str = Field(
        description="Structural locator or pointer where the change occurred (e.g. responses['200'] or requestBody.content['application/json'].schema.properties.name)"
    )
    description: str = Field(
        description="Human-readable explanation of what changed and its contract impact"
    )
    old_value: Any = Field(
        default=None,
        description="The value or declaration present in the baseline specification (null if added)",
    )
    new_value: Any = Field(
        default=None,
        description="The value or declaration present in the candidate specification (null if removed)",
    )
```

---

## 3. DiffSummary

Aggregate metrics summarizing the comparison between the two specification versions. Used when rendering the `--summary` table to `stderr`.

```python
class DiffSummary(BaseModel):
    """Summary statistics for changes detected across two specifications."""

    model_config = ConfigDict(extra="forbid")

    total_changes: int = Field(default=0, description="Total count of all detected change records")
    breaking_changes: int = Field(default=0, description="Count of changes with breaking=True")
    operations_added: int = Field(
        default=0, description="Count of newly added operations (breaking=False)"
    )
    operations_removed: int = Field(
        default=0, description="Count of discontinued operations (breaking=True)"
    )
    schema_breaking_changes: int = Field(
        default=0,
        description="Count of breaking schema and response modifications across shared operations (breaking=True)",
    )

    @property
    def has_breaking_changes(self) -> bool:
        """Return True if any breaking changes were detected."""
        return self.breaking_changes > 0
```

---

## 4. Entity Relationships & Lifecycle

```
[Baseline Spec File]  ---> load_openapi_spec() ---> Old Spec Dict ---> OperationExtractor
                                                                          |
                                                                          v
                                                                 Old Operation Chunks
                                                                          |
                                                                          v
[Candidate Spec File] ---> load_openapi_spec() ---> New Spec Dict ---> DiffEngine
                                                                          |
                                                                          +--> Match Operations (Method + Normalized Path)
                                                                          |    +-> Operation Added (breaking: false)
                                                                          |    +-> Operation Removed (breaking: true)
                                                                          |
                                                                          +--> Diff Shared Operation Schemas
                                                                          |    +-> Required Request Property Added (breaking: true)
                                                                          |    +-> Response Property Removed (breaking: true)
                                                                          |    +-> Response Status Removed (2xx only) (breaking: true)
                                                                          |    +-> Field Type Changed (breaking: true)
                                                                          |    +-> Enum Value Removed (breaking: true)
                                                                          |
                                                                          v
                                                             List / Stream of DiffChangeRecord
                                                                          |
                                                       +------------------+------------------+
                                                       |                                     |
                                                       v                                     v
                                               stdout: JSONL lines             stderr: DiffSummary Table (if --summary)
                                                       |                                     |
                                                       +------------------+------------------+
                                                                          |
                                                                          v
                                                               Process Exit Code (0, 1, or 2)
```
