"""Domain models and Pydantic schemas for SpecProbe chunks and statistics."""

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ChunkMetadata(BaseModel):
    """Metadata describing an isolated API operation chunk."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="The endpoint URI template (e.g. /api/v1/users/{id})")
    method: str = Field(description="Uppercase HTTP method (GET, POST, PUT, DELETE, etc.)")
    tags: list[str] = Field(default_factory=list, description="Associated operation tags")
    operationId: str = Field(description="Unique operation identifier (explicit or synthesized)")
    security: list[dict[str, list[str]]] = Field(
        default_factory=list,
        description="Resolved security requirements (operation-level or global fallback)",
    )
    deprecated: bool = Field(default=False, description="Flag indicating if operation is deprecated")
    source_title: str = Field(default="Untitled API", description="Source specification title")
    source_version: str = Field(default="0.0.0", description="Source specification version")
    estimated_tokens: int = Field(default=0, description="Approximate token count of chunk")
    warnings: list[str] = Field(
        default_factory=list,
        description="Warning notices specific to this chunk",
    )


class OperationChunk(BaseModel):
    """A self-contained chunk representing a single API operation with pruned schemas."""

    model_config = ConfigDict(extra="forbid")

    metadata: ChunkMetadata = Field(description="Operational metadata block")
    operation: dict[str, Any] = Field(description="Normalized operation definition with merged parameters")
    components: dict[str, Any] = Field(
        default_factory=dict,
        description="Pruned components dictionary containing only referenced schemas",
    )


class ChunkingStats(BaseModel):
    """Summary statistics for chunking across an entire specification."""

    model_config = ConfigDict(extra="forbid")

    total_operations: int = Field(description="Total operations extracted across all paths")
    min_tokens: int = Field(description="Smallest chunk token size encountered")
    max_tokens: int = Field(description="Largest chunk token size encountered")
    median_tokens: float = Field(description="Median chunk token size")
    avg_tokens: float = Field(description="Arithmetic mean of chunk token sizes")
    oversized_chunks: int = Field(description="Count of chunks exceeding the token budget")
    warnings: list[str] = Field(
        default_factory=list,
        description="Comprehensive list of all warnings emitted across all chunks",
    )
