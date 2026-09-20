"""Pydantic data models for generated API test cases."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "RequestFixture",
    "ResponseAssertion",
    "GeneratedTestCase",
]


class RequestFixture(BaseModel):
    """Concrete input fixtures for executing the API request."""

    model_config = ConfigDict(extra="ignore")

    method: str | None = Field(
        default=None,
        description="HTTP request method (e.g. GET, POST, PUT, DELETE).",
    )
    path: str | None = Field(
        default=None,
        description="Endpoint URI path template (e.g. /pets/{petId}).",
    )
    path_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Resolved path parameters substituting placeholders in the endpoint path.",
    )
    query_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Query string parameters conforming to the endpoint schema.",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="HTTP request headers (e.g. Content-Type, Accept).",
    )
    body: Any | None = Field(
        default=None,
        description="Concrete request body payload conforming to the endpoint request schema.",
    )


class ResponseAssertion(BaseModel):
    """Verification assertions for evaluating the API response."""

    model_config = ConfigDict(extra="ignore")

    status_code: int = Field(
        ge=100,
        le=599,
        description="Expected HTTP response status code (targeting 2xx success).",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Expected response headers (e.g. Content-Type).",
    )
    schema_shape: dict[str, Any] | None = Field(
        default=None,
        description="Expected JSON schema structure or expected field assertions for the response.",
    )


class GeneratedTestCase(BaseModel):
    """Traceable, executable API test case definition."""

    model_config = ConfigDict(extra="ignore")

    operation_id: str = Field(
        min_length=1,
        description="Traceable identifier of the target API operation.",
    )
    description: str = Field(
        min_length=1,
        description="Plain-language description of the test scenario.",
    )
    request: RequestFixture = Field(
        description="Proposed request fixtures.",
    )
    response: ResponseAssertion = Field(
        description="Expected response assertions.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Operational tags inherited from the OpenAPI specification.",
    )
