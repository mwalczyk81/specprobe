# Research: Deterministic Export for Runnable Test Artifacts

**Feature**: `004-export-test-artifacts`  
**Date**: 2026-09-19  
**Status**: Complete  

---

## 1. Postman Collection v2.1.0 Format

### Context
Postman Collection Schema v2.1.0 (`https://schema.getpostman.com/json/collection/v2.1.0/collection.json`) is the standard format recognized by Postman desktop, Postman web, and Newman CLI test runners.

### Decisions
1. **Schema & Collection Structure**:
   - `info`: Contains `name`, `schema` (fixed to `https://schema.getpostman.com/json/collection/v2.1.0/collection.json`), and deterministic `_postman_id` derived via `uuid.uuid5(uuid.NAMESPACE_URL, f"specprobe:{collection_name}")` to ensure byte-identical output across repeated runs (Constitution Principle II).
   - `variable`: Top-level variable definition array containing `{"key": "baseUrl", "value": base_url, "type": "string"}`.
   - `item`: Hierarchical array of folder objects or direct request items.

2. **Tag-Based Folder Grouping**:
   - Folders are created for each unique primary tag (`test_case.tags[0]`).
   - If an operation has multiple tags, it is assigned exclusively to the first tag's folder, preventing test case duplication in runners like Newman.
   - Operations without tags are placed directly in the root `item` array (or in a dedicated "Default" folder if other requests are grouped in folders; placing untagged requests in root `item` alongside folder objects is fully valid per Postman v2.1 schema).

3. **URL Representation & Path Parameter Substitution**:
   - Path parameters from `request.path_params` are substituted directly into the path string using standard RFC 3986 URL encoding (`urllib.parse.quote(str(value), safe="")`).
   - The Postman `url` object is serialized with both:
     - `raw`: e.g. `{{baseUrl}}/pets/42?limit=10`
     - `host`: `["{{baseUrl}}"]`
     - `path`: `["pets", "42"]`
     - `query`: `[{"key": "limit", "value": "10"}]`
   - This dual raw + structured URL representation guarantees compatibility across both desktop Postman UI and headless Newman runners.

4. **Request Body Mapping**:
   - When `request.body` is present and non-null:
     - `mode`: `"raw"`
     - `raw`: Formatted JSON string (`json.dumps(body, indent=2, ensure_ascii=False)`)
     - `options`: `{"raw": {"language": "json"}}`
   - When `request.body` is null or absent, the `body` field is omitted from the request object.

5. **Test Scripts (`pm.test`) & Traceability**:
   - Embedded under `event` array with `listen: "test"`.
   - Script `type`: `"text/javascript"`.
   - Generates executable assertion lines:
     - Status code assertion:
       ```javascript
       pm.test("Status code is 200", function () {
           pm.response.to.have.status(200);
       });
       ```
     - Header assertion (if headers specified in response assertion):
       ```javascript
       pm.test("Header Content-Type is present", function () {
           pm.response.to.have.header("Content-Type");
       });
       ```
     - Schema shape property assertions (resolved in clarification Q3):
       ```javascript
       pm.test("Response has expected properties", function () {
           var jsonData = pm.response.json();
           pm.expect(jsonData).to.have.property("id");
           pm.expect(jsonData).to.have.property("name");
       });
       ```
   - Traceability: Request name is set to `description` (or `[<operation_id>] <description>`), and request `description` explicitly records `Operation: <operation_id>`.

### Alternatives Considered
- *Using Postman URL path variables (`:petId`) instead of direct substitution*: Postman path variables require an extra `variable` sub-array per request and don't always resolve cleanly in lightweight HTTP runners. Direct substitution into `{{baseUrl}}/pets/42` is immediately runnable and cleaner.
- *Strict Ajv `pm.response.to.have.jsonSchema` validation*: Rejected during clarification in favor of property-level checks via `pm.expect(jsonData).to.have.property(...)`, which are more resilient to partial schema definitions.

---

## 2. VS Code REST Client (`.http`) Format

### Context
The VS Code REST Client extension (and equivalent JetBrains HTTP Client) parses plain-text `.http` files according to RFC 7230 formatting.

### Decisions
1. **Top-Level Variable Declaration**:
   - The file begins with `@baseUrl = <base_url>` (defaulting to `http://localhost:8000` or the user's `--base-url`).
2. **Request Delimiters**:
   - Each test case is separated by a standard delimiter line: `###`.
3. **Comment Documentation Header**:
   - Includes metadata before the request line:
     ```http
     ###
     # @name listPets
     # Operation: listPets
     # Description: List all pets
     # Expected Status: 200
     # Expected Properties: id, name, tag
     ```
4. **HTTP Request Line & Headers**:
   - Request line: `<METHOD> {{baseUrl}}/<path> HTTP/1.1`
   - Parameter substitution matches Postman (URL-encoded path parameters).
   - Headers: One header per line (`Header-Name: header-value`).
   - Query parameters appended to the URL string.
5. **Request Body**:
   - Follows HTTP standard: separated from headers by exactly one blank line.
   - Formatted as canonical JSON (`json.dumps(body, indent=2, ensure_ascii=False)`).

### Alternatives Considered
- *Omission of `@baseUrl` variable*: Hardcoding URLs directly removes the ability for developers to change target host at the top of the file. Using `@baseUrl` is standard REST Client practice.

---

## 3. Determinism & Zero-LLM Guarantees (Constitution Principle II)

### Context
Constitution Principle II dictates that artifact generation must be 100% deterministic and never call an LLM.

### Decisions
1. **Key Sorting & Serialization**:
   - Postman JSON output MUST be serialized with deterministic formatting:
     - `json.dumps(collection, indent=2, ensure_ascii=False)`
     - Stable dictionary key ordering for all metadata, folders, and request objects.
2. **Deterministic IDs**:
   - Collection `_postman_id` uses `uuid.uuid5` with a fixed namespace and collection name seed.
   - No timestamps, random UUIDs (`uuid4`), or environment-dependent values in exported files.
3. **Deterministic Regression Tests (Principle VI)**:
   - Golden-file regression tests will compare exporter output against static reference fixtures for OpenAPI samples, verifying character-for-character / structure-for-structure equality.

---

## 4. Architecture & Module Placement

### Context
Existing codebase has:
- `src/specprobe/chunker/`
- `src/specprobe/index/`
- `src/specprobe/search/`
- `src/specprobe/generator/`
- `src/specprobe/models.py`
- `src/specprobe/cli.py`

### Decisions
1. **Module Location**: Create `src/specprobe/exporter/` package:
   - `src/specprobe/exporter/models.py`: Export configuration domain models.
   - `src/specprobe/exporter/postman.py`: Deterministic Postman Collection v2.1.0 generator.
   - `src/specprobe/exporter/http_client.py`: Deterministic REST Client `.http` file generator.
   - `src/specprobe/exporter/engine.py`: Orchestrator that loads `GeneratedTestCase` records from file or stdin and delegates to formatters.
2. **CLI Command**:
   - Implement `@cli.command("export")` in `src/specprobe/cli.py`.
   - Supports:
     - `[test_cases_file]` argument (optional, defaults to `sys.stdin`).
     - `--format {postman,http,both}` (default: `both`).
     - `--output <path>` (optional for single format, required directory for `both`).
     - `--collection-name <name>` (optional).
     - `--base-url <url>` (optional, default: `http://localhost:8000`).
