# Research & Technical Decisions: Environment File Export

**Feature Branch**: `010-env-file-export`  
**Date**: 2026-09-21  
**Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/010-env-file-export/spec.md)

---

## 1. Postman Environment Format (v2.1)

### Decision
Emit native Postman v2.1 environment files named `<sanitized_env_name>.postman_environment.json` alongside `collection.json` when Postman format is selected.

### Schema Details
Postman environments use the following JSON schema:
```json
{
  "id": "<deterministic-uuid>",
  "name": "<env_name>",
  "values": [
    {
      "key": "baseUrl",
      "value": "http://localhost:8000",
      "enabled": true,
      "type": "default"
    },
    {
      "key": "apiKey",
      "value": "<api_key>",
      "enabled": true,
      "type": "default"
    }
  ],
  "_postman_variable_scope": "environment"
}
```
- **ID Generation**: `uuid.uuid5(uuid.NAMESPACE_URL, f"specprobe:env:{env_name}")` guarantees deterministic IDs across runs for identical environment names.
- **Scope**: `_postman_variable_scope: "environment"` ensures Postman correctly imports the file as an environment artifact rather than a collection or globals file.
- **Collection Decoupling**: When environment files are exported, `collection.json`'s top-level `"variable"` list omits `baseUrl` and security variables, relying on the imported environment to resolve `{{baseUrl}}` and `{{schemeName}}`.

### Alternatives Considered
- *Inlining environment variables inside collection variables*: Rejected because it prevents switching environments in Postman workspaces and bakes specific host URLs into version control.
- *Postman Globals file (`globals.postman_globals.json`)*: Rejected because variables would bleed across unrelated collections in the workspace rather than being scoped to the target environment.

---

## 2. VS Code REST Client Environment Format (`http-client.env.json`)

### Decision
Emit a single `http-client.env.json` configuration file in the same directory as `requests.http` when REST Client format is selected.

### Schema Details
VS Code REST Client recognizes a JSON file named `http-client.env.json` placed in the same directory as the `.http` file or in the workspace root:
```json
{
  "local": {
    "baseUrl": "http://localhost:8000",
    "apiKey": "<api_key>"
  },
  "work": {
    "baseUrl": "https://api.work.internal",
    "apiKey": "<api_key>"
  }
}
```
- **File Variable Decoupling**: In `requests.http`, top-level declarations (`@baseUrl = ...` and `@schemeName = ...`) are omitted.
- **Reference Integrity**: Request blocks already reference `{{baseUrl}}` in the request line and `{{schemeName}}` in headers/query params. These references resolve dynamically via VS Code's environment picker (bottom right status bar or Cmd/Ctrl+Alt+E).

### Alternatives Considered
- *Multiple `.http` files per environment (`requests.local.http`, `requests.work.http`)*: Rejected because it causes file explosion, duplicates test maintenance, and defeats REST Client's native environment mechanism.
- *Dotenv files (`.env`)*: Rejected because VS Code REST Client's native multi-environment selector uses `http-client.env.json`.

---

## 3. CLI Interface & Environment Parsing

### Decision
Provide two complementary input mechanisms for defining environments on `specprobe export`:
1. Repeatable `--env <name>=<url>` option on the CLI (e.g. `--env local=http://localhost:8000 --env work=https://api.work.internal`).
2. Optional `--env-file <path>` option supporting JSON (`.json`) and YAML (`.yaml`, `.yml`).

### Precedence & Merging Rules
1. If `--env-file` is specified, it is read and validated first.
2. If `--env` flags are provided, they are parsed and merged into the environment map. If an environment name is defined in both `--env-file` and `--env`, the CLI `--env` flag takes precedence.
3. If neither `--env` nor `--env-file` is provided, legacy `--base-url <url>` is treated as shorthand for `--env default=<url>`, ensuring complete backward compatibility without breaking existing scripts.
4. If duplicate `--env` flags are provided with the same name, the CLI raises a `click.UsageError`.
5. If `--env` or `--env-file` is used and `--output` is omitted (stdout streaming), the CLI exits with code 1 and writes `Error: Option '--output' is required when exporting environments.` to `stderr`.
6. If `--output` points to a file (e.g. `out/collection.json`), environment files are written to `output.parent` (`out/`).

### Configuration File Schema for `--env-file`
Supports either a dictionary of environments or a list of environment objects:
```yaml
# YAML format
local:
  baseUrl: "http://localhost:8000"
  apiKey: "dev-key-12345"
work:
  baseUrl: "https://api.work.internal"
  apiKey: "staging-secret-abc"
```
Or JSON:
```json
{
  "local": {
    "baseUrl": "http://localhost:8000",
    "apiKey": "dev-key-12345"
  }
}
```

---

## 4. Credential Resolution & Placeholder Strategy

### Decision
Reuse `SecurityResolver.default_placeholder` (`<token>`, `<api_key>`, `<credentials>`) directly for credential variable values in generated environment files when not explicitly overridden.

### Mechanics
1. Inspect test cases to extract unique parameterized security schemes (skipping negative auth test cases per Feature 007).
2. For each unique scheme, obtain `cred.variable_name` (e.g. `apiKey`) and `cred.default_placeholder` (e.g. `<api_key>`).
3. In each environment file, set the variable's value to the user-supplied value from `--env-file` if present; otherwise default to `cred.default_placeholder`.
4. Negative auth cases continue using inline invalid literal values on the request itself without touching variables.

---

## 5. Summary of Architecture Changes

| Component | Changes |
|-----------|---------|
| `specprobe.exporter.models` | Add `ExportEnvironment` model; update `ExportConfig` with `environments: list[ExportEnvironment]` and `env_file: Path \| None`. |
| `specprobe.exporter.postman` | Add `generate_postman_environment(env, test_cases)`; update `generate_postman_collection` to support variable suppression. |
| `specprobe.exporter.http_client` | Add `generate_rest_client_environments(envs, test_cases)`; update `generate_http_document` to omit variable header when environments are exported. |
| `specprobe.exporter.engine` | Orchestrate environment file serialization to target directory / parent directory across single and dual formats. |
| `specprobe.cli` | Add `--env` and `--env-file` options to `export_command`; parse and validate environment inputs, handle backward compatibility, and enforce `--output` requirement. |
