"""Pydantic data models for generated API test cases."""

import re
from typing import Any

from jsonschema import Draft7Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "RequestFixture",
    "ResponseAssertion",
    "GeneratedTestCase",
]

_LOCAL_REF_PATTERN = re.compile(r"^#/(\$defs|definitions)/([^/]+)$")

# Keys that, if present at the top level of a schema_shape, indicate it actually
# constrains something. A schema with none of these (e.g. only "$defs"/"definitions",
# or purely descriptive metadata) is a no-op assertion at runtime: Ajv accepts anything
# against it, so pm.response.to.have.jsonSchema() passes regardless of the response body.
_MEANINGFUL_SCHEMA_KEYS = {
    "type",
    "$ref",
    "properties",
    "items",
    "enum",
    "const",
    "anyOf",
    "oneOf",
    "allOf",
    "not",
    "required",
    "pattern",
    "format",
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "additionalProperties",
    "patternProperties",
}


def _find_unresolvable_refs(node: Any, local_defs: set[str]) -> list[str]:
    """Recursively collect every '$ref' pointer in a schema tree that cannot resolve
    within the schema's own 'definitions'/'$defs' block.

    A schema_shape must be fully self-contained: Postman's Ajv engine evaluates it in
    isolation, with no access to the source OpenAPI document, so an OpenAPI-style
    pointer like '#/components/schemas/Pet' can never resolve, wherever it appears in
    the tree (a bare top-level $ref, or nested inside 'items', 'properties', etc.).
    """
    unresolvable: list[str] = []
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            match = _LOCAL_REF_PATTERN.match(ref)
            if not match or match.group(2) not in local_defs:
                unresolvable.append(ref)
        for key, value in node.items():
            if key == "$ref":
                continue
            unresolvable.extend(_find_unresolvable_refs(value, local_defs))
    elif isinstance(node, list):
        for item in node:
            unresolvable.extend(_find_unresolvable_refs(item, local_defs))
    return unresolvable


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
        description="Expected JSON schema structure conforming strictly to JSON Schema Draft 7.",
    )

    @field_validator("schema_shape")
    @classmethod
    def validate_schema_shape(cls, v: Any) -> dict[str, Any] | None:
        """Validate that schema_shape conforms to JSON Schema Draft 7 and is self-contained."""
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError(f"schema_shape must be a dictionary or None, got {type(v).__name__}")

        try:
            Draft7Validator.check_schema(v)
        except SchemaError as err:
            raise ValueError(f"Invalid JSON Schema Draft 7 structure: {err.message}") from err

        # Self-contained guarantee: reject any $ref anywhere in the tree (bare top-level,
        # or nested inside "items", "properties", "anyOf", etc.) that doesn't resolve to
        # a local "$defs"/"definitions" entry within this same schema_shape document.
        # This runs BEFORE the "meaningful content" check below so a bare unresolved
        # $ref (e.g. {"$ref": "#/components/schemas/Pet"}) gets the specific, actionable
        # "unresolvable $ref" message rather than the generic one -- the retry prompt is
        # built from this exact error text, and the model needs to know it's the $ref
        # that's the problem, not just that the schema lacks a "type".
        local_defs = set(v.get("$defs", {})) | set(v.get("definitions", {}))
        unresolvable_refs = _find_unresolvable_refs(v, local_defs)
        if unresolvable_refs:
            raise ValueError(
                f"schema_shape contains unresolvable $ref pointer(s) {unresolvable_refs} "
                "that do not resolve to a local '$defs'/'definitions' entry within this "
                "schema. Schemas must be self-contained: inline structural definitions or "
                "reference a local '#/$defs/<name>' entry, never an OpenAPI-document-relative "
                "pointer like '#/components/schemas/...'."
            )

        # Reject schemas with no actual validation content, e.g. {"$defs": {"Pet": {...}}}
        # with nothing referencing "Pet" via "type"/"properties"/"items"/"$ref". This is
        # syntactically valid Draft 7 (an unconstrained schema matches anything) but it
        # means the generated assertion silently validates nothing. Any unresolvable
        # $ref was already caught above, so a "$ref" reaching this point is known to
        # resolve locally and counts as meaningful content in its own right.
        if not (_MEANINGFUL_SCHEMA_KEYS & v.keys()):
            raise ValueError(
                "schema_shape has no meaningful validation content: it must declare at "
                "least one of "
                f"{sorted(_MEANINGFUL_SCHEMA_KEYS)}. A schema containing only "
                "'$defs'/'definitions' (unreferenced) or metadata keys is a no-op "
                "assertion at runtime — inline the definitions into 'type'/'properties'/"
                "'items' instead of leaving them unused."
            )

        return v


class GeneratedTestCase(BaseModel):
    """Traceable, executable API test case definition."""

    model_config = ConfigDict(extra="ignore")

    test_type: str = Field(
        default="positive",
        description="Discriminator for positive vs negative test scenarios.",
    )
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
    security: list[dict[str, list[str]]] = Field(
        default_factory=list,
        description="Resolved security requirements inherited from the target operation chunk.",
    )
    security_schemes: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Resolved security scheme definitions inherited from operation chunk components."
        ),
    )

    @field_validator("test_type")
    @classmethod
    def validate_test_type(cls, v: str) -> str:
        """Validate that test_type is one of the supported discriminators."""
        allowed = {"positive", "negative_auth_missing", "negative_auth_invalid"}
        if v not in allowed:
            raise ValueError(f"Invalid test_type '{v}'. Must be one of {sorted(allowed)}.")
        return v
