# CLI Contract: `specprobe diff`

**Command**: `specprobe diff`
**Feature Branch**: `013-diff-spec-versions`
**Date**: 2026-10-03
**Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/013-diff-spec-versions/spec.md)

---

## 1. Command Syntax

```bash
specprobe diff [OPTIONS] OLD_SPEC NEW_SPEC
```

### Positional Arguments
- `OLD_SPEC` *(required)*: Path to the baseline OpenAPI 3.0 or 3.1 specification file (`.json` or `.yaml` / `.yml`), or `-` for standard input.
- `NEW_SPEC` *(required)*: Path to the candidate OpenAPI 3.0 or 3.1 specification file (`.json` or `.yaml` / `.yml`).

### Options
- `--summary`: *(flag, default: False)* Render a formatted Rich summary table of detected changes to `stderr`.
- `--help`: Show help message and exit.

---

## 2. Streams & I/O Protocol

### Standard Output (`stdout`)
- Streams line-delimited JSON (`JSONL`), emitting exactly one JSON object per detected structural change record conforming to `DiffChangeRecord`.
- If no changes are detected, `stdout` remains empty (zero lines).
- Never polluted with log messages, progress bars, or summary tables.

### Standard Error (`stderr`)
- Emits diagnostic messages, file validation errors, and the optional summary table when `--summary` is enabled.
- If `--summary` is enabled, prints a Rich table displaying:
  - Total changes detected
  - Total breaking changes detected
  - Added operations count
  - Removed operations count
  - Breaking schema changes broken down by category

---

## 3. Process Exit Codes

| Exit Code | Meaning | Condition |
|---|---|---|
| `0` | Clean / No Breaking Changes | Diff succeeded and found zero breaking changes (`breaking: false` additions or zero changes). |
| `1` | Breaking Changes Detected | Diff succeeded and detected one or more breaking changes (`breaking: true`). |
| `2` | Execution Error | Input file not found, permission denied, invalid YAML/JSON syntax, or unsupported OpenAPI version. |

---

## 4. Example Invocations

### Basic streaming JSONL diff
```bash
specprobe diff api-v1.yaml api-v2.yaml
```

### Piping JSONL into jq
```bash
specprobe diff api-v1.yaml api-v2.yaml | jq 'select(.breaking == true)'
```

### Diff with human-readable summary
```bash
specprobe diff api-v1.yaml api-v2.yaml --summary
```

### Using as a CI pull-request validation gate
```bash
specprobe diff baseline.json candidate.json --summary
# Exit code is 1 if any breaking changes were detected, terminating CI runner with failure
```
