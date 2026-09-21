# Data Model: Negative Authentication Test Cases (401/403)

**Feature Branch**: `007-negative-auth-tests`
**Date**: 2026-09-20
**Status**: Completed

## 1. Entity Overview

```mermaid
classDiagram
    class OperationChunk {
        +OperationMetadata metadata
        +dict[str, Any] components
        +dict[str, Any] parameters
        +dict[str, Any] request_body
        +dict[str, Any] responses
    }

    class GeneratedTestCase {
        +str test_type
        +str operation_id
        +str description
        +RequestFixture request
        +ResponseAssertion response
        +list[str] tags
        +list[dict] security
        +dict security_schemes
    }

    class RequestFixture {
        +str method
        +str path
        +dict[str, Any] path_params
        +dict[str, Any] query_params
        +dict[str, str] headers
        +Any body
    }

    class ResponseAssertion {
        +int status_code
        +dict[str, str] headers
        +dict[str, Any] schema_shape
    }

    OperationChunk --> GeneratedTestCase : synthesizes (LLM)
    GeneratedTestCase --> GeneratedTestCase : derives 401 & 403 (Zero-LLM)
    GeneratedTestCase *-- RequestFixture
    GeneratedTestCase *-- ResponseAssertion
```

---

## 2. Core Entities

### 2.1 Extended `GeneratedTestCase`

Model location: `src/specprobe/generator/models.py`

| Field | Type | Default | Description |
|---|---|---|---|
| `test_type` | `str` | `"positive"` | Discriminator identifying scenario purpose: `"positive"`, `"negative_auth_missing"`, or `"negative_auth_invalid"`. |
| `operation_id` | `str` | *required* | OpenAPI operation identifier ensuring strict traceability per Principle V. |
| `description` | `str` | *required* | Human-readable explanation of the test scenario. |
| `request` | `RequestFixture` | *required* | Concrete HTTP request fixtures (method, path, headers, query, body). |
| `response` | `ResponseAssertion` | *required* | Expected response assertions (status code, headers, schema). |
| `tags` | `list[str]` | `[]` | OpenAPI operation tags, preserving primary folder tag first. |
| `security` | `list[dict[str, list[str]]]` | `[]` | Security requirements declared on the target operation. |
| `security_schemes` | `dict[str, Any]` | `{}` | Resolved scheme components referenced by security requirements. |

#### Validation Rules:
- `test_type` must be one of: `"positive"`, `"negative_auth_missing"`, `"negative_auth_invalid"`.
- For `test_type == "negative_auth_missing"`, `response.status_code` must be `401`.
- For `test_type == "negative_auth_invalid"`, `response.status_code` must be `403`.
- For `test_type == "positive"`, `response.status_code` must be `2xx` (100–299).

---

### 2.2 Mutation Specifications

#### HTTP 401 (`negative_auth_missing`)
- **Intent**: Verify unauthenticated request rejection.
- **Trigger**: Operation defines at least one non-empty security requirement.
- **Transformation Rules**:
  - `test_type` set to `"negative_auth_missing"`.
  - `response.status_code` set to `401`.
  - `response.schema_shape` set to documented 401 schema in operation chunk if available, otherwise `None`.
  - `description` formatted as: `"[401] Missing authentication credentials - {operation_id}"`.
  - `tags` prepends original tags and appends `["negative", "auth", "401"]`.
  - `request.headers`: Strips all headers associated with any security scheme defined in `chunk.metadata.security` (e.g. `Authorization`, `X-API-Key`).
  - `request.query_params`: Strips all query parameters associated with any security scheme defined in `chunk.metadata.security`.
  - `request.path_params` and `request.body`: Retained unchanged from the happy-path fixture.

#### HTTP 403 (`negative_auth_invalid`)
- **Intent**: Verify rejection of invalid or corrupted credentials.
- **Trigger**: Operation defines at least one non-empty security requirement.
- **Transformation Rules**:
  - `test_type` set to `"negative_auth_invalid"`.
  - `response.status_code` set to `403`.
  - `response.schema_shape` set to documented 403 schema in operation chunk if available, otherwise `None`.
  - `description` formatted as: `"[403] Invalid authentication credentials - {operation_id}"`.
  - `tags` prepends original tags and appends `["negative", "auth", "403"]`.
  - `request.headers` / `request.query_params`: Injects protocol-valid invalid literals for the primary winning scheme:
    - **Bearer / OAuth2 / OpenIDConnect**: `Authorization: Bearer invalid_token`
    - **HTTP Basic**: `Authorization: Basic aW52YWxpZDppbnZhbGlk`
    - **API Key (Header)**: `<header_name>: invalid_<name>_key`
    - **API Key (Query)**: `<param_name>=invalid_<name>_key`
    - **Cookie**: `Cookie: <name>=invalid_<name>_token`

---

## 3. Serialization & Export Mapping

### 3.1 Postman Collection v2.1 Mapping

| Test Case Attribute | Postman Serialization Mapping |
|---|---|
| `test_type == "positive"` | Request item named `<description>`. Header/query parameterized with `{{<var>}}`. Asserts `200` (or `2xx`) + JSON Schema. |
| `test_type == "negative_auth_missing"` | Sibling item in same tag folder, named `[401] <description>`. Auth header/query omitted. Asserts `pm.response.to.have.status(401)`. No JSON Schema assertion unless defined. |
| `test_type == "negative_auth_invalid"` | Sibling item in same tag folder, named `[403] <description>`. Auth header/query contains raw inline invalid literal (e.g. `Bearer invalid_token`). Asserts `pm.response.to.have.status(403)`. |
| Collection Variables | Aggregated **only** from `test_type == "positive"` test cases. Negative test cases contribute no collection variables. |

### 3.2 REST Client (`.http`) Mapping

| Test Case Attribute | REST Client Serialization Mapping |
|---|---|
| `test_type == "positive"` | Block `# @name <op_id>`, `# Expected Status: 2xx`, `@<var> = <placeholder>` at top of file, request line with `{{<var>}}`. |
| `test_type == "negative_auth_missing"` | Block `# @name <op_id>_401`, `# Expected Status: 401`, request line with all auth headers/query params omitted. |
| `test_type == "negative_auth_invalid"` | Block `# @name <op_id>_403`, `# Expected Status: 403`, request line with inline invalid literal (e.g. `Authorization: Bearer invalid_token`). |
| Top-level File Variables | Aggregated **only** from `test_type == "positive"` test cases (`@baseUrl`, `@<schemeName> = <placeholder>`). |
