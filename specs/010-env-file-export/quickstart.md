# Quickstart & Validation Guide: Environment File Export

**Feature Branch**: `010-env-file-export`  
**Date**: 2026-09-21  
**Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/010-env-file-export/spec.md)

---

## 1. Prerequisites

Ensure dependencies and virtual environment are up-to-date:
```shell
uv sync
```

---

## 2. Validation Scenarios

### Scenario 1: Multi-Environment Dual Export (`--format both`)
Export test cases targeting `local` and `work` environments simultaneously into an output directory:

```shell
uv run specprobe export tests/fixtures/generated_tests.jsonl \
    --format both \
    -o ./out_both \
    --env local=http://localhost:8000 \
    --env work=https://api.work.internal
```

**Expected Files in `./out_both`**:
- `collection.json` (Postman collection v2.1)
- `requests.http` (VS Code REST Client test document)
- `local.postman_environment.json`
- `work.postman_environment.json`
- `http-client.env.json`

**Verification Checks**:
1. Check `requests.http`: Must NOT contain `@baseUrl = ...` or `@apiKey = ...` in the file header.
2. Check `http-client.env.json`: Must contain root keys `"local"` and `"work"` with correct `baseUrl` values.
3. Check `local.postman_environment.json`: Must contain `"name": "local"` and `baseUrl` set to `http://localhost:8000`.

---

### Scenario 2: REST Client Export with Single File Destination
Export `.http` directly to a target file path:

```shell
uv run specprobe export tests/fixtures/generated_tests.jsonl \
    --format http \
    -o ./out_rest/suite.http \
    --env staging=https://staging.example.com
```

**Expected Files in `./out_rest`**:
- `suite.http`
- `http-client.env.json` (placed in `./out_rest/` alongside `suite.http`)

---

### Scenario 3: Postman Export with `--env-file` Configuration
Export Postman collection using a YAML configuration file:

Create `./environments.yaml`:
```yaml
dev:
  baseUrl: "http://localhost:3000"
  apiKey: "dev-key-xyz"
prod:
  baseUrl: "https://api.production.internal"
```

Run export:
```shell
uv run specprobe export tests/fixtures/generated_tests.jsonl \
    --format postman \
    -o ./out_postman \
    --env-file ./environments.yaml
```

**Expected Files in `./out_postman`**:
- `collection.json`
- `dev.postman_environment.json` (with `apiKey` = `"dev-key-xyz"`)
- `prod.postman_environment.json` (with `apiKey` = `"<api_key>"`)

---

### Scenario 4: Error on Missing `--output` when Environments Active
Verify that attempting to export environments without an output destination fails fast:

```shell
uv run specprobe export tests/fixtures/generated_tests.jsonl \
    --format http \
    --env local=http://localhost:8000
```

**Expected Output**:
- Exit code `1`
- `stderr`: `Error: Option '--output' is required when exporting environments.`

---

### Scenario 5: Legacy Backward Compatibility
Run export with only `--base-url`:

```shell
uv run specprobe export tests/fixtures/generated_tests.jsonl \
    --format both \
    -o ./out_compat \
    --base-url http://custom-host:9000
```

**Expected Output**:
- Exit code `0`
- `./out_compat/` contains `default.postman_environment.json` and `http-client.env.json` with a `default` entry pointing to `http://custom-host:9000`.
