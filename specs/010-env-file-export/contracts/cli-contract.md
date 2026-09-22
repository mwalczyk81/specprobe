# CLI Contract: `specprobe export` with Environments

**Feature Branch**: `010-env-file-export`  
**Date**: 2026-09-21  
**Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/010-env-file-export/spec.md)

---

## 1. Command Synopsis

```shell
specprobe export [OPTIONS] [TEST_CASES_FILE]
```

---

## 2. Options Specification

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `TEST_CASES_FILE` | `Path \| None` | `None` (or `-` for stdin) | Path to JSONL generated test cases file. |
| `--format` | `[postman\|http\|both]` | `both` | Target export format. |
| `-o, --output` | `Path \| None` | `None` | Output file path (single format) or directory (both formats or when exporting environments). |
| `--collection-name` | `str \| None` | `None` | Custom name for Postman collection. |
| `--base-url` | `str` | `http://localhost:8000` | Legacy fallback base URL (treated as shorthand for `--env default=<url>` if no `--env` or `--env-file` provided). |
| `--env` | `list[str]` (repeatable) | `[]` | Define a named environment in `<name>=<url>` format. Repeatable for multiple environments. |
| `--env-file` | `Path \| None` | `None` | Path to a JSON (`.json`) or YAML (`.yaml`, `.yml`) environment configuration file. |

---

## 3. CLI Validation & Precedence Rules

1. **Missing `--output` when Environments Active**:
   - If `--env` or `--env-file` is provided, `--output` MUST be specified.
   - If `--output` is missing: exit with code 1 and emit:
     `Error: Option '--output' is required when exporting environments.` to `stderr`.
2. **Output Path Resolution**:
   - If `--format both`: `--output` MUST be a directory path (created if absent).
   - If `--format postman` or `--format http`:
     - If `--output` is a directory: artifacts are written into that directory (`collection.json`, `requests.http`, `*.postman_environment.json`, `http-client.env.json`).
     - If `--output` is a file path (e.g. `out/my_test.http`): the primary artifact is written to that file path, and environment files are written to its parent directory (`out/http-client.env.json`).
3. **Environment Syntax Validation**:
   - Each `--env <val>` must contain at least one `=` separator.
   - The `<name>` before the `=` must not be empty.
   - The `<url>` after the `=` must not be empty.
   - Malformed syntax (e.g. `--env invalid`) exits with code 1 and emits `Error: Invalid environment format '<val>'. Expected '<name>=<url>'.` to `stderr`.
4. **Duplicate Environment Rejection**:
   - If the same environment name appears more than once across `--env` flags, the CLI exits with code 1 and emits `Error: Duplicate environment name '<name>' specified.` to `stderr`.
5. **Merging Precedence**:
   - If both `--env-file` and `--env` are specified:
     - `--env-file` is parsed first.
     - CLI `--env` entries merge into the environment list. If an environment name exists in both, the CLI `--env` definition overrides the file entry.
6. **`--env-file` Validation**:
   - Must exist on disk (enforced via Click `exists=True`).
   - Extension must be `.json`, `.yaml`, or `.yml`. Unrecognized extension exits with code 1 and emits `Error: Unsupported environment file extension '<ext>'. Expected .json, .yaml, or .yml.` to `stderr`.
   - Malformed JSON/YAML exits with code 1 and emits `Error: Failed to parse environment file: <details>` to `stderr`.
7. **Legacy Backward Compatibility**:
   - If neither `--env` nor `--env-file` is passed, `--base-url <url>` is treated as shorthand for `--env default=<url>`.
   - If `--output` is supplied, a single `default` environment file is emitted alongside the primary collection/`.http` file.

---

## 4. Exit Codes

| Exit Code | Meaning |
|-----------|---------|
| `0` | Success: test cases exported and environment files written. |
| `1` | Error: invalid arguments, missing required `--output`, unreadable files, schema errors, or parsing failures. |
