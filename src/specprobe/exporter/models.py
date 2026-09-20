"""Domain models and configuration for test artifact exporting."""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ExportFormat(StrEnum):
    """Supported export artifact formats."""

    POSTMAN = "postman"
    HTTP = "http"
    BOTH = "both"


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
