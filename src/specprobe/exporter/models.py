"""Domain models and configuration for test artifact exporting."""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExportFormat(StrEnum):
    """Supported export artifact formats."""

    POSTMAN = "postman"
    HTTP = "http"
    BOTH = "both"


class ExportEnvironment(BaseModel):
    """Named environment configuration for export."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the environment (e.g. 'local', 'work', 'staging')",
    )
    base_url: str = Field(
        ...,
        min_length=1,
        description="Target API server root URL for this environment",
    )
    variables: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Optional custom variable mappings (e.g. credentials, tokens) for this environment"
        ),
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Environment name cannot be empty or blank")
        return trimmed

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        trimmed = v.strip().rstrip("/")
        if not trimmed:
            raise ValueError("Environment base_url cannot be empty or blank")
        return trimmed


class ExportConfig(BaseModel):
    """Runtime configuration for specprobe export command."""

    model_config = ConfigDict(extra="forbid")

    format: ExportFormat = Field(
        default=ExportFormat.BOTH, description="Target export artifact format(s)"
    )
    output_path: Path | None = Field(
        default=None,
        description="Destination output file path (for single format) or directory (for both)",
    )
    collection_name: str | None = Field(
        default=None, description="Custom title/name for exported Postman collection"
    )
    base_url: str = Field(
        default="http://localhost:8000",
        description="Base URL for target API environment embedded as variable",
    )
    environments: list[ExportEnvironment] = Field(
        default_factory=list,
        description="List of resolved target environments to emit as environment files",
    )
    env_file: Path | None = Field(
        default=None,
        description="Path to user-supplied JSON or YAML environment configuration file",
    )
