"""Shared Pydantic domain models for SpecProbe search matches, indexing payloads,
and diagnostics.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from specprobe.chunker.models import ChunkingStats, ChunkMetadata, OperationChunk

__all__ = [
    "ChunkMetadata",
    "OperationChunk",
    "ChunkingStats",
    "SearchMatch",
    "SpecStatBreakdown",
    "IndexStatsReport",
]


class SearchMatch(BaseModel):
    """An operation search match returned by specprobe search."""

    model_config = ConfigDict(extra="ignore")

    operationId: str = Field(description="Unique OpenAPI operationId")
    path: str = Field(description="Endpoint URI template")
    method: str = Field(description="Uppercase HTTP method (e.g. GET, POST)")
    score: float = Field(
        description="Ordinal relevance score valid only within current search call"
    )
    tags: list[str] = Field(default_factory=list, description="Associated operation tags")
    summary: str | None = Field(
        default=None, description="Short human-readable summary of operation"
    )
    source_title: str = Field(description="Originating API specification title")
    source_version: str = Field(description="Originating API specification version")
    chunk: dict[str, Any] | None = Field(
        default=None,
        description="Complete OperationChunk data payload (included only when --full is specified)",
    )


class SpecStatBreakdown(BaseModel):
    """Chunk count and metadata breakdown for a single API specification."""

    model_config = ConfigDict(extra="forbid")

    source_title: str = Field(description="Originating API specification title")
    source_version: str = Field(description="Originating API specification version")
    chunk_count: int = Field(description="Number of active indexed operation points")


class IndexStatsReport(BaseModel):
    """Collection health and summary metrics reported by specprobe index --stats."""

    model_config = ConfigDict(extra="forbid")

    total_operations: int = Field(description="Total operations stored in active collection")
    unique_specifications: int = Field(
        description="Count of distinct (source_title, source_version) specs"
    )
    specifications: list[SpecStatBreakdown] = Field(
        default_factory=list,
        description="Per-specification breakdown of indexed operations",
    )
    vector_dimensions: dict[str, Any] = Field(
        default_factory=dict,
        description="Configurations and dimensions of dense and sparse vectors",
    )
    index_path: str = Field(description="Absolute path to on-disk index storage")
    status: str = Field(description="Overall index health status ('healthy' or 'empty')")
