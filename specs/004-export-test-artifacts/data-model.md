# Data Model: Test Artifact Exporter

**Feature**: `004-export-test-artifacts`
**Date**: 2026-09-19
**Status**: Complete

---

## 1. Input Entity: `GeneratedTestCase`

The exporter directly consumes `GeneratedTestCase` instances (defined in `specprobe.generator.models`), serialized as JSON Lines.

```text
GeneratedTestCase
├── operation_id: str           (Required identifier of target API operation)
├── description: str            (Plain-language description of happy-path scenario)
├── request: RequestFixture
│   ├── path_params: dict       (Concrete parameter values to substitute into URL)
│   ├── query_params: dict      (Key-value query parameters)
│   ├── headers: dict           (HTTP headers to send with request)
│   └── body: Any | None        (Structured JSON payload, or None)
├── response: ResponseAssertion
│   ├── status_code: int        (Expected HTTP status code, e.g. 200, 201)
│   ├── headers: dict           (Expected response headers, e.g. Content-Type)
│   └── schema_shape: dict|None (Structural attributes or JSON schema expectations)
└── tags: list[str]             (Categorization tags inherited from operation)
```

---

## 2. Exporter Configuration Model

```python
class ExportFormat(StrEnum):
    POSTMAN = "postman"
    HTTP = "http"
    BOTH = "both"


class ExportConfig(BaseModel):
    """Runtime configuration for specprobe export command."""

    format: ExportFormat = ExportFormat.BOTH
    output_path: Path | None = None
    collection_name: str | None = None
    base_url: str = "http://localhost:8000"
```

---

## 3. Postman Collection v2.1.0 Data Entities

Mapping `GeneratedTestCase` to the official Postman Collection Schema v2.1.0:

```text
PostmanCollection
├── info: PostmanInfo
│   ├── _postman_id: str        (Deterministic UUIDv5: "specprobe:{collection_name}")
│   ├── name: str               (User collection name or derived from spec metadata)
│   ├── schema: str             ("https://schema.getpostman.com/json/collection/v2.1.0/collection.json")
│   └── description: str | None (Summary documentation)
├── variable: list[PostmanVariable]
│   └── key="baseUrl", value=base_url, type="string"
└── item: list[PostmanFolder | PostmanItem]
    ├── [PostmanFolder]         (Grouped by primary tag: tags[0])
    │   ├── name: str           (Tag name, e.g. "pets")
    │   └── item: list[PostmanItem]
    └── [PostmanItem]           (Direct items for untagged operations)
        ├── name: str           (Test case description)
        ├── request: PostmanRequest
        │   ├── method: str     (GET, POST, PUT, DELETE, etc.)
        │   ├── header: list    (PostmanHeader entries)
        │   ├── body: PostmanBody | None (mode="raw", language="json", raw string)
        │   ├── url: PostmanUrl (raw, host=["{{baseUrl}}"], path, query)
        │   └── description: str ("Operation: <operation_id>\n\n<description>")
        └── event: list[PostmanEvent]
            └── listen="test", script=PostmanScript(exec=[...pm.test assertions...])
```

### URL Template Substitution
- Template: `/pets/{petId}` with `path_params={"petId": 42}`
- Substituted: `{{baseUrl}}/pets/42`
- URL Encoding: Every path parameter value is escaped with `urllib.parse.quote(str(val), safe="")` to preserve URL syntax.

### Postman Test Script Rules
- **Status Assertion**: Always generated.
  ```javascript
  pm.test("Status code is <status_code>", function () {
      pm.response.to.have.status(<status_code>);
  });
  ```
- **Header Assertions**: Generated for each entry in `response.headers`.
  ```javascript
  pm.test("Header <header> is present", function () {
      pm.response.to.have.header("<header>");
  });
  ```
- **Property Assertions**: Generated for top-level keys in `response.schema_shape` (or top-level properties list).
  ```javascript
  pm.test("Response has expected properties", function () {
      var jsonData = pm.response.json();
      pm.expect(jsonData).to.have.property("<prop1>");
      pm.expect(jsonData).to.have.property("<prop2>");
  });
  ```

---

## 4. REST Client (`.http`) Data Entities

The plain-text REST Client model represents RFC 7230 request blocks:

```text
HttpDocument
├── base_url: str               (Emitted as top-level variable: @baseUrl = <url>)
└── requests: list[HttpRequestBlock]
    ├── operation_id: str       (# @name <operation_id>, # Operation: <operation_id>)
    ├── description: str        (# Description: <description>)
    ├── expected_status: int    (# Expected Status: <status_code>)
    ├── expected_properties: list (# Expected Properties: <prop1>, <prop2>)
    ├── method: str             (HTTP method: GET, POST, etc.)
    ├── path_url: str           (Target URL: {{baseUrl}}/pets/42)
    ├── query_params: dict      (Appended as ?key=val)
    ├── headers: dict           (Formatted one per line)
    └── body: str | None        (JSON string separated by blank line)
```

### Serialization Format
```http
@baseUrl = http://localhost:8000

###
# @name listPets
# Operation: listPets
# Description: List all pets
# Expected Status: 200
# Expected Properties: id, name, tag
GET {{baseUrl}}/pets?limit=10 HTTP/1.1
Accept: application/json

###
# @name createPet
# Operation: createPet
# Description: Create a new pet
# Expected Status: 201
POST {{baseUrl}}/pets HTTP/1.1
Content-Type: application/json

{
  "name": "Fido",
  "tag": "dog"
}
```
