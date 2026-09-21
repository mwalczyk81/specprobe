# CLI & Interface Contract: Negative Authentication Tests

**Feature Branch**: `007-negative-auth-tests`
**Date**: 2026-09-20
**Status**: Completed

## 1. CLI Contract: `specprobe generate`

### Usage
```bash
specprobe generate [OPTIONS] [RESULTS_FILE]
```

### Options
| Option | Type | Default | Description |
|---|---|---|---|
| `RESULTS_FILE` | Argument | `None` (reads stdin) | JSON search results file from `specprobe search --full`. Pass `-` or omit to read from stdin. |
| `--model` | Option | `SPECPROBE_LLM_MODEL` or `"local-model"` | Model identifier routed via LiteLLM. |
| `--api-base` | Option | `SPECPROBE_LLM_API_BASE` or `"http://localhost:1234/v1"` | LiteLLM base URL endpoint. |
| `--temperature` | Option | `0.2` | Sampling temperature for happy-path generation. |
| `--cache-dir` | Option | `".specprobe/cache"` | Directory for cryptographic disk caching. |
| `--no-cache` | Flag | `False` | Bypass cache lookup. |
| `--negative-auth` / `--no-negative-auth` | Flag | `True` (**NEW**) | Enable or disable deterministic 401/403 negative test case generation for secured operations. |

### Exit Codes
- `0`: Success (at least 1 operation succeeded or empty input processed cleanly).
- `1`: Failure (all operations failed, file not found, or input invalid).

### Output Contract
Standard Output (`stdout`) streams newline-delimited JSON (`JSONL`), where each line is a valid `GeneratedTestCase` JSON object.
When `--negative-auth` is enabled (default):
- Secured operations yield 3 JSONL lines:
  1. Happy path (`test_type: "positive"`, status 2xx)
  2. Missing credentials (`test_type: "negative_auth_missing"`, status 401)
  3. Invalid credentials (`test_type: "negative_auth_invalid"`, status 403)
- Unsecured operations (`security: []` or omitted) yield exactly 1 JSONL line:
  1. Happy path (`test_type: "positive"`, status 2xx)

---

## 2. CLI Contract: `specprobe export`

### Usage
```bash
specprobe export [OPTIONS] [TEST_CASES_FILE]
```

### Options
| Option | Type | Default | Description |
|---|---|---|---|
| `TEST_CASES_FILE` | Argument | `None` (reads stdin) | Path to JSONL file from `specprobe generate`. Pass `-` or omit to read stdin. |
| `-f`, `--format` | Choice: `postman`, `http`, `both` | `"both"` | Output format to generate. |
| `-o`, `--output-dir` | Path | `.` | Target directory for generated artifact files. |
| `--collection-name` | String | `"SpecProbe Generated Collection"` | Name for Postman collection. |
| `--base-url` | String | `"http://localhost:8000"` | Base URL variable value. |

### Postman Artifact Contract
- Schema: Postman Collection v2.1.0 (`https://schema.getpostman.com/json/collection/v2.1.0/collection.json`)
- Structure:
  - Folders grouped by primary tag.
  - Sibling items inside tag folder:
    - Happy path: `[Operation Name]`
    - 401 Missing Auth: `[401] [Operation Name]` (auth stripped, asserts `status(401)`)
    - 403 Invalid Auth: `[403] [Operation Name]` (inline invalid literal, asserts `status(403)`)
  - Variables: `baseUrl` and sanitized scheme variables populated with placeholders (`<token>`, `<api_key>`). Negative tests introduce no additional collection variables.

### REST Client (`.http`) Artifact Contract
- Syntax: RFC 7230 request blocks separated by `###`.
- Structure:
  - Top-level `@baseUrl` and `@<schemeName>` variables.
  - Happy path: `# @name <operation_id>`, `# Expected Status: 200`, `Authorization: Bearer {{<schemeName>}}`.
  - 401 Missing Auth: `# @name <operation_id>_401`, `# Expected Status: 401`, no authorization headers.
  - 403 Invalid Auth: `# @name <operation_id>_403`, `# Expected Status: 403`, inline invalid literal (e.g. `Authorization: Bearer invalid_token`).
