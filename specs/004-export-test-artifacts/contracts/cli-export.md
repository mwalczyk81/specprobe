# CLI Contract: `specprobe export`

**Command**: `specprobe export`  
**Parent Group**: `specprobe`  
**Purpose**: Deterministically transform `GeneratedTestCase` JSONL records into runnable Postman Collections and/or REST Client `.http` files without invoking an LLM.

---

## 1. Syntax

```bash
specprobe export [TEST_CASES_FILE] [OPTIONS]
```

---

## 2. Arguments

| Argument | Type | Required | Description |
|---|---|---|---|
| `TEST_CASES_FILE` | Path (`click.Path(dir_okay=False, allow_dash=True)`) | Optional | Path to JSONL file containing `GeneratedTestCase` objects. If omitted or passed as `-`, reads from standard input (`stdin`). |

---

## 3. Options

| Option | Type | Default | Description |
|---|---|---|---|
| `--format` | Choice: `postman`, `http`, `both` | `both` | Target artifact format(s) to generate. |
| `-o`, `--output` | Path (`click.Path()`) | `None` | Destination output file path (for single format) or directory path (for `--format both`). If omitted for a single format, outputs to `stdout`. |
| `--collection-name` | String | `None` | Title/name for Postman collection. If omitted, derived from test case metadata or defaults to `"SpecProbe Generated Collection"`. |
| `--base-url` | String | `http://localhost:8000` | Target host base URL embedded as `{{baseUrl}}` in Postman variables and `@baseUrl` in `.http` file. |

---

## 4. Exit Codes & Streams

| Exit Code | Condition | Output Stream |
|---|---|---|
| `0` | Success: artifact(s) successfully generated. | `stdout` (for single format without `--output`) or designated file(s). Progress/info on `stderr`. |
| `0` | Empty input: 0 test cases supplied. Produces valid empty collection / empty file. | `stdout` or designated file(s), notice on `stderr`. |
| `1` | Input validation error: missing file, malformed JSONL, non-conforming test case schema. | Descriptive error message on `stderr`. |
| `1` | Invalid options: `--format both` specified without `--output <dir>`. | Error message explaining directory requirement on `stderr`. |
| `1` | Filesystem error: destination cannot be written or created. | Error message on `stderr`. |

---

## 5. Output Schemas

### Single Format to stdout (`--format postman`)
Emits valid, formatted Postman Collection v2.1.0 JSON:
```json
{
  "info": {
    "_postman_id": "...",
    "name": "...",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "variable": [
    { "key": "baseUrl", "value": "http://localhost:8000", "type": "string" }
  ],
  "item": []
}
```

### Single Format to stdout (`--format http`)
Emits plain-text RFC 7230 REST Client content:
```http
@baseUrl = http://localhost:8000

###
# @name ...
GET {{baseUrl}}/... HTTP/1.1
```

### Dual Format to Directory (`--format both --output <dir>`)
Creates two files in `<dir>`:
- `<dir>/collection.json`
- `<dir>/requests.http`
Emits summary notice on `stderr`:
```text
Exported 4 test cases to <dir>/collection.json and <dir>/requests.http
```
