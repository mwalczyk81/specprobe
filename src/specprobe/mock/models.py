"""Pydantic data models for the local mock HTTP server."""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

__all__ = [
    "MockResponse",
    "MockRoute",
    "MockServerConfig",
    "MockAccessLogEntry",
]


class MockResponse(BaseModel):
    """Concrete canned HTTP response served by the mock server."""

    status_code: int = Field(
        ...,
        ge=100,
        le=599,
        description="HTTP status code to return (e.g. 200, 201, 204).",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="HTTP response headers to emit (e.g. {'Content-Type': 'application/json'}).",
    )
    body: bytes = Field(
        default=b"",
        description="Pre-serialized byte payload to write to the HTTP response stream.",
    )


class MockRoute(BaseModel):
    """Registered mock route representing an available endpoint."""

    method: str = Field(
        ...,
        description="Uppercase HTTP method (e.g. 'GET', 'POST', 'PUT', 'DELETE').",
    )
    path: str = Field(
        ...,
        description="Normalized URI path with resolved path parameters (e.g. '/pets/42').",
    )
    path_template: str | None = Field(
        default=None,
        description=(
            "Normalized path template (e.g. '/pets/{petId}') that also matches any concrete "
            "value in each placeholder segment; None for routes served at 'path' only."
        ),
    )
    operation_id: str = Field(
        ...,
        description="Traceable identifier of the target API operation.",
    )
    response: MockResponse = Field(
        ...,
        description="Canned response served upon request match.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Operational tags inherited from GeneratedTestCase.",
    )


class MockServerConfig(BaseModel):
    """Configuration options for initializing the MockServer."""

    host: str = Field(
        default="127.0.0.1",
        description="Network host interface to bind (default: '127.0.0.1' / 'localhost').",
    )
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="TCP port to bind (default: 8000).",
    )
    input_source: Path | str = Field(
        ...,
        description="File path to test cases JSONL or '-' for standard input.",
    )


class MockAccessLogEntry(BaseModel):
    """Record of a processed HTTP request."""

    timestamp: datetime = Field(
        ...,
        description="Timestamp when the request was received.",
    )
    method: str = Field(
        ...,
        description="HTTP method of the incoming request.",
    )
    path: str = Field(
        ...,
        description="Requested URI path (excluding query string).",
    )
    status_code: int = Field(
        ...,
        description="HTTP response status code returned.",
    )
    latency_ms: float = Field(
        ...,
        ge=0.0,
        description="Time taken to process and respond in milliseconds.",
    )
    matched: bool = Field(
        ...,
        description="True if request matched a registered route; False if 404/405.",
    )
