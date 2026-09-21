# Phase 1 Data Model: Security-Scheme-Aware Authentication

**Feature**: `006-security-scheme-auth`
**Date**: 2026-09-20
**Status**: Completed

---

## 1. Domain Entities & Schemas

### 1.1 `SecuritySchemeDefinition` (OpenAPI Component Schema)

Represents an OpenAPI 3.0/3.1 security scheme defined under `components.securitySchemes`.

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | `str` | Yes | Authentication type: `"http"`, `"apiKey"`, `"oauth2"`, or `"openIdConnect"`. |
| `description` | `str | None` | No | Optional human-readable description of the scheme. |
| `name` | `str | None` | Conditional | Name of the header or query parameter (required when `type="apiKey"`). |
| `in` | `str | None` | Conditional | Parameter transport location: `"header"`, `"query"`, or `"cookie"` (required when `type="apiKey"`). |
| `scheme` | `str | None` | Conditional | HTTP authorization scheme: `"bearer"` or `"basic"` (required when `type="http"`). |
| `bearerFormat` | `str | None` | No | Hint for bearer token format (e.g. `"JWT"`). |
| `flows` | `dict[str, Any] | None` | Conditional | OAuth2 flow configurations mapping flow types to scopes (present when `type="oauth2"`). |

---

### 1.2 `SecurityRequirement` (Operation Security Mandate)

Represents an operation's security requirement item as defined in OpenAPI (`list[dict[str, list[str]]]`).

```python
# Type Alias
SecurityRequirement = dict[str, list[str]]
SecurityRequirementsList = list[SecurityRequirement]
```

- Each dictionary in the list represents an alternative security requirement (logical OR).
- If the list contains an empty dictionary `{}`, authentication is optional for that operation (`FR-013`).
- Multiple keys within a single dictionary represent a compound security requirement requiring all specified schemes simultaneously (logical AND, `FR-006`).
- The dictionary values are lists of required OAuth2 scope strings (e.g. `["read:pets", "write:pets"]`).

---

### 1.3 `ResolvedCredential` (Internal Exporter Intermediate Representation)

Encapsulates the resolved authentication credential for a test case, ready for serialization into Postman collection variables and REST Client file variables.

```python
@dataclass(frozen=True)
class ResolvedCredential:
    """Resolved credential binding for test case export."""

    scheme_name: str
    """Original OpenAPI security scheme identifier (e.g., 'apiKeyAuth')."""

    variable_name: str
    """Sanitized identifier for Postman {{...}} and .http @... variables."""

    transport: Literal["header", "query"]
    """Transport mechanism for the credential."""

    target_name: str
    """Header name (e.g., 'Authorization', 'X-API-Key') or query parameter name."""

    wire_value_template: str
    """Value expression with variable placeholder (e.g., 'Bearer {{bearerAuth}}')."""

    default_placeholder: str
    """Initial placeholder value for collection/file variable (e.g., '<token>')."""

    is_optional: bool = False
    """True if requirement was specified alongside an empty {} alternative."""

    scopes: list[str] = field(default_factory=list)
    """List of required OAuth2 scopes."""

    alternatives: list[str] = field(default_factory=list)
    """Other available alternative scheme names that were not selected."""
```

---

## 2. Updated Core Models

### 2.1 `OperationChunk` (`src/specprobe/chunker/models.py`)

`OperationChunk.components` now explicitly preserves pruned `securitySchemes` alongside `schemas`:

```python
class OperationChunk(BaseModel):
    """A self-contained chunk representing a single API operation with pruned schemas."""

    model_config = ConfigDict(extra="forbid")

    metadata: ChunkMetadata = Field(description="Operational metadata block")
    operation: dict[str, Any] = Field(
        description="Normalized operation definition with merged parameters"
    )
    components: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Pruned components dictionary containing referenced schemas and "
            "referenced security scheme definitions ('securitySchemes')."
        ),
    )
```

### 2.2 `GeneratedTestCase` (`src/specprobe/generator/models.py`)

`GeneratedTestCase` incorporates optional security fields to carry resolved requirement metadata to downstream exporters without requiring source spec re-reading:

```python
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
    security: list[dict[str, list[str]]] = Field(
        default_factory=list,
        description="Resolved security requirements inherited from the target operation chunk.",
    )
    security_schemes: dict[str, Any] = Field(
        default_factory=dict,
        description="Resolved security scheme definitions inherited from operation chunk components.",
    )
```

---

## 3. Data Transformations & Life Cycle

```
[OpenAPI Spec]
      │
      ▼
OperationExtractor (prunes components.securitySchemes to match op security)
      │
      ▼
OperationChunk (contains metadata.security + components["securitySchemes"])
      │
      ▼
PromptBuilder (formats Security Requirements into LLM user prompt)
      │
      ▼
GenerationEngine (populates GeneratedTestCase.security and security_schemes)
      │
      ▼
GeneratedTestCase (JSONL on stdout or file)
      │
      ▼
SecurityResolver (resolves priority order, sanitizes names, determines variable bindings)
      │
      ├──► Postman Serializer (declares root collection variable, uses {{schemeName}})
      └──► REST Client Serializer (declares top @schemeName =, adds # Security comments)
```

---

## 4. Validation Rules

1. **Deterministic Selection Priority (`FR-005`)**:
   - `http` (scheme: `bearer`) or `oauth2` > `apiKey` (`in: header`) > `apiKey` (`in: query`) > `http` (scheme: `basic`).
2. **Variable Name Sanitization (`FR-007`, `FR-008`)**:
   - Scheme identifiers are stripped of characters outside `[a-zA-Z0-9_]`. Leading digits are prefixed with `_`.
3. **Compound Requirements (`FR-006`)**:
   - If a requirement dict has multiple keys `{"apiKey1": [], "apiKey2": []}`, a `ResolvedCredential` is generated for each scheme in the dict.
4. **Scope Extraction (`FR-014`)**:
   - OAuth2 scopes are collected and formatted as `# Scopes: scope1, scope2`.
5. **Deduplication (`FR-010`)**:
   - Collection variables and `.http` file variables are keyed by `variable_name`, guaranteeing exactly one declaration per unique scheme.
