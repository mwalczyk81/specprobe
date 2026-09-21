# Quickstart Validation Guide: Security-Scheme-Aware Authentication

**Feature**: `006-security-scheme-auth`
**Date**: 2026-09-20

This guide provides end-to-end validation steps to verify security-scheme-aware authentication across the entire SpecProbe pipeline (`chunk` -> `search` -> `generate` -> `export`).

---

## Prerequisites

1. Active Python environment managed with `uv`:
   ```bash
   uv sync
   ```
2. Working test specification containing diverse security schemes:
   - `tests/fixtures/specs/security_schemes.json` (contains Bearer, Basic, API Key header/query, OAuth2 with scopes, optional security `{}`)

---

## Scenario 1: Verify Pruned Security Schemes in Operation Chunks

Validate that `specprobe chunk` preserves referenced `components.securitySchemes` in `OperationChunk.components`:

```bash
uv run specprobe chunk tests/fixtures/specs/security_schemes.json --op getBearerResource
```

**Expected Outcome**:
- Output JSON contains chunk with:
  - `metadata.security` populated with resolved requirements (`[{"bearerAuth": []}]`).
  - `components.securitySchemes` containing the corresponding definitions (`{"type": "http", "scheme": "bearer"}`).

---

## Scenario 2: Verify Security Placeholders in Generated Test Cases

Validate that `specprobe generate` includes security placeholders in generated request fixtures:

```bash
uv run specprobe chunk tests/fixtures/specs/security_schemes.json --op getBearerResource | \
uv run specprobe generate --no-cache
```

**Expected Outcome**:
- Emitted `GeneratedTestCase` JSONL includes:
  - `request.headers` or `request.query_params` populated with appropriate credential placeholder (`Authorization: Bearer <token>` or `<api_key>`).
  - `security` and `security_schemes` fields populated with operation security metadata.

---

## Scenario 3: Verify Parameterized Postman Collection Export

Validate that `specprobe export --format postman` declares collection variables and parameterizes request headers:

```bash
uv run specprobe chunk tests/fixtures/specs/security_schemes.json | \
uv run specprobe generate --no-cache | \
uv run specprobe export --format postman --output dist/postman_test.json
```

**Inspection**:
```bash
cat dist/postman_test.json
```

**Expected Outcome**:
- Collection `variable` array contains `{"key": "<schemeName>", "value": "<token>" | "<api_key>", "type": "string"}`.
- Request headers/urls reference `{{<schemeName>}}`.
- Requests with optional security annotate description with `Security: <schemeName> (optional)`.

---

## Scenario 4: Verify Parameterized REST Client (.http) Export

Validate that `specprobe export --format http` declares top-level file variables and comment annotations:

```bash
uv run specprobe chunk tests/fixtures/specs/security_schemes.json | \
uv run specprobe generate --no-cache | \
uv run specprobe export --format http --output dist/http_test.http
```

**Inspection**:
```bash
cat dist/http_test/*.http
```

**Expected Outcome**:
- File header contains:
  ```http
  @baseUrl = http://localhost:8000
  @<schemeName> = <token>
  ```
- Request blocks contain:
  ```http
  # Security: <schemeName>
  # Scopes: <scopes> (if OAuth2)
  # Alternatives: <alts> (if alternatives exist)
  GET {{baseUrl}}/path HTTP/1.1
  Authorization: Bearer {{<schemeName>}}
  ```

---

## Scenario 5: Full Automated Test Suite & Quality Gates

Verify that all automated unit, integration, and golden-file regression tests pass offline:

```bash
# Unit & Integration Tests
uv run pytest tests/ -v

# Static Type Checking
uv run ty check src/

# Code Hygiene & Linting
uv run pre-commit run --all-files
```

**Expected Outcome**:
- 100% of tests pass cleanly.
- `ty check src/` completes with 0 diagnostics.
- `pre-commit` passes all hooks.
