# Environment Schemas Contract

**Feature Branch**: `010-env-file-export`
**Date**: 2026-09-21
**Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/010-env-file-export/spec.md)

---

## 1. Postman Environment v2.1 Schema

### File Naming Convention
`<sanitized_env_name>.postman_environment.json`
(e.g., `local.postman_environment.json`, `staging.postman_environment.json`)

### Structure Definition
```json
{
  "$schema": "https://schema.getpostman.com/json/collection/v2.1.0/environment.json",
  "id": "7b6efb46-7734-58e1-a07c-9cf1dfc5031b",
  "name": "local",
  "values": [
    {
      "key": "apiKey",
      "value": "<api_key>",
      "type": "default",
      "enabled": true
    },
    {
      "key": "baseUrl",
      "value": "http://localhost:8000",
      "type": "default",
      "enabled": true
    }
  ],
  "_postman_variable_scope": "environment"
}
```

### Constraints & Invariants
- `id`: Deterministic UUIDv5 generated via `uuid.uuid5(uuid.NAMESPACE_URL, f"specprobe:env:{env_name}")`.
- `name`: Matches the environment identifier.
- `values`: Array of variable objects sorted alphabetically by `key`.
  - Always includes `baseUrl` with the target host.
  - Includes all parameterized security scheme variables detected in non-negative test cases.
  - Credential values default to `cred.default_placeholder` (`<token>`, `<api_key>`, `<credentials>`), or explicit values from `--env-file`.
- `_postman_variable_scope`: Literal string `"environment"`.

---

## 2. VS Code REST Client `http-client.env.json` Schema

### File Naming Convention
`http-client.env.json` (exact filename required by VS Code REST Client extension)

### Structure Definition
```json
{
  "local": {
    "apiKey": "<api_key>",
    "baseUrl": "http://localhost:8000"
  },
  "work": {
    "apiKey": "<api_key>",
    "baseUrl": "https://api.work.internal"
  }
}
```

### Constraints & Invariants
- Root object keys are environment names (e.g. `"local"`, `"work"`, `"default"`), sorted alphabetically.
- Child object keys are variable names, sorted alphabetically.
- Always includes `"baseUrl"`.
- Includes all parameterized security scheme variables with values defaulting to `default_placeholder` or `--env-file` overrides.
- No surrounding arrays or wrapper envelopes; pure dictionary-of-dictionaries JSON.

---

## 3. `--env-file` Input Configuration Schema

### File Extensions
`.json`, `.yaml`, `.yml`

### YAML Example
```yaml
local:
  baseUrl: "http://localhost:8000"
  apiKey: "my-local-key"
  bearerAuth: "mock-token-abc"

work:
  baseUrl: "https://api.work.internal"
  apiKey: "internal-corp-key"
```

### JSON Example
```json
{
  "local": {
    "baseUrl": "http://localhost:8000",
    "apiKey": "my-local-key"
  },
  "work": {
    "baseUrl": "https://api.work.internal",
    "apiKey": "internal-corp-key"
  }
}
```

### Validation Rules
- Must be a dictionary where each top-level key is an environment name.
- Each environment value must be a dictionary.
- Must contain `baseUrl` (or `base_url`).
- Additional keys are treated as credential variable overrides.
