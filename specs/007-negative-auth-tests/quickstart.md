# Quickstart Validation Guide: Negative Authentication Tests (401/403)

**Feature Branch**: `007-negative-auth-tests`
**Date**: 2026-09-20
**Status**: Ready for Implementation

This guide provides runnable end-to-end validation scenarios demonstrating that negative authentication test cases (401 missing credentials, 403 invalid credentials) are deterministically generated and correctly exported to Postman and REST Client artifacts.

---

## 1. Prerequisites

- Python 3.11+ installed with `uv`
- Repository dependencies synced:
  ```powershell
  uv sync --all-groups
  ```

---

## 2. Validation Scenario 1: Generate Negative Auth Tests via CLI

Verify that `specprobe generate` automatically emits 401 and 403 negative test cases for secured operations by default, and disables them with `--no-negative-auth`.

### Step 1: Generate with Default Settings (Negative Auth Enabled)
Using pre-recorded search results for a secured specification (e.g. Petstore with `api_key` or Bearer auth):
```powershell
uv run specprobe generate tests/fixtures/search_results_secured.json > test_cases_with_neg.jsonl
```

### Expected Outcome:
- Each secured operation produces 3 JSONL records:
  - 1 happy-path test case (`test_type: "positive"`, `response.status_code: 200`)
  - 1 missing-auth negative case (`test_type: "negative_auth_missing"`, `response.status_code: 401`, stripped auth headers)
  - 1 invalid-auth negative case (`test_type: "negative_auth_invalid"`, `response.status_code: 403`, inline invalid literal)
- Unsecured operations produce only 1 happy-path test case.

### Step 2: Generate with `--no-negative-auth` (Opt-Out)
```powershell
uv run specprobe generate --no-negative-auth tests/fixtures/search_results_secured.json > test_cases_happy_only.jsonl
```

### Expected Outcome:
- Exactly 1 test case per operation (`test_type: "positive"`, `response.status_code: 200`), identical to Feature 006 output.

---

## 3. Validation Scenario 2: Export Postman Collection with Negative Tests

Verify that `specprobe export` serializes 401 and 403 test cases as sibling items inside the operation's tag folder with status assertions.

### Run Command:
```powershell
uv run specprobe export test_cases_with_neg.jsonl -f postman -o output/
```

### Expected Outcome in `output/postman_collection.json`:
- Sibling requests in each tag folder:
  - `[Operation Name]` asserting `pm.response.to.have.status(200)`
  - `[401] [Operation Name]` asserting `pm.response.to.have.status(401)` with no auth header/variable
  - `[403] [Operation Name]` asserting `pm.response.to.have.status(403)` with inline invalid literal (e.g., `Authorization: Bearer invalid_token`)
- Collection `variable` section contains only `baseUrl` and real scheme placeholders (`<token>`, `<api_key>`). No `invalid` variables are added.

---

## 4. Validation Scenario 3: Export VS Code REST Client (.http)

Verify that `.http` export generates RFC 7230 request blocks with negative status comments and inline invalid credentials.

### Run Command:
```powershell
uv run specprobe export test_cases_with_neg.jsonl -f http -o output/
```

### Expected Outcome in `output/api_requests.http`:
- Top-level variables define `@baseUrl` and `@<schemeName> = <token>`.
- Request blocks for each secured operation:
  - `# @name <op_id>` with `# Expected Status: 200` and `{{<schemeName>}}`
  - `# @name <op_id>_401` with `# Expected Status: 401` and auth headers omitted
  - `# @name <op_id>_403` with `# Expected Status: 403` and inline corrupted literal (e.g. `Authorization: Bearer invalid_token`)

---

## 5. Validation Scenario 4: Automated Verification Gates

Run the full project test suite and quality gates:
```powershell
uv run ruff check .
uv run ruff format --check .
uv run ty check src/
uv run pytest
```

### Expected Outcome:
- Zero lint errors, zero format diffs, zero type check diagnostics.
- 100% of existing tests (242+) plus new negative auth tests pass cleanly.
