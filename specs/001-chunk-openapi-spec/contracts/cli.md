# Interface Contract: `specprobe chunk` CLI

This document details the command-line interface contract for the `chunk` command in `specprobe`.

---

## Command Signature

```bash
specprobe chunk [OPTIONS] SPEC_FILE
```

### Positional Arguments
- `SPEC_FILE` (Required): Path to an OpenAPI 3.0.x or 3.1.x specification file formatted in YAML or JSON. If `-` is passed, reads from standard input (`stdin`).

### Options

| Option | Type | Default | Description |
|---|---|---|---|
| `--max-tokens` | Integer | `2000` | Configurable token budget threshold. Chunks with token counts exceeding this value trigger an overage warning. |
| `--op` | String | `None` | Target `operationId` to spot check. When provided, the CLI outputs only that single chunk formatted as JSON. |
| `--stats` | Flag | `False` | Exclusive summary mode. Prints a human-readable table of operation counts, token size distribution, and warnings to `stdout` instead of streaming chunks. |
| `--help` | Flag | `N/A` | Show Click help message and exit. |

---

## Output Behavior & Streams

### 1. Default Mode (No `--stats`, No `--op`)
- **`stdout`**: Emits newline-delimited JSON (JSON Lines / JSONL). Each line is an independent, valid JSON object representing one `OperationChunk`.
- **`stderr`**: Emits advisory warnings (e.g., token budget exceeded, unsupported external references encountered).
- **Exit Code**: `0` on success (even if non-fatal warnings are emitted).

#### Example `stdout` Line:
```json
{"metadata":{"path":"/api/v1/users/{id}","method":"GET","tags":["Users"],"operationId":"getUserById","security":[{"bearerAuth":[]}],"deprecated":false,"source_title":"User API","source_version":"1.0.0","estimated_tokens":320,"warnings":[]},"operation":{"summary":"Retrieve user by ID","parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}],"responses":{"200":{"description":"Success","content":{"application/json":{"schema":{"$ref":"#/components/schemas/User"}}}}}},"components":{"schemas":{"User":{"type":"object","properties":{"id":{"type":"string"},"name":{"type":"string"}}}}}}
```

### 2. Spot Check Mode (`--op <operationId>`)
- **`stdout`**: Outputs a single indented, human-readable JSON object representing the targeted `OperationChunk`.
- **`stderr`**: Emits error message if the `operationId` is not found.
- **Exit Code**: `0` if found; `1` if not found.

### 3. Exclusive Stats Mode (`--stats`)
- **`stdout`**: Displays a formatted text table summarizing operations and chunk sizes:
  ```text
  SpecProbe Chunking Statistics: User API (1.0.0)
  =============================================================
  Total Operations:      42
  Min Chunk Size:        180 tokens
  Max Chunk Size:        2,450 tokens
  Median Chunk Size:     410 tokens
  Average Chunk Size:    530.2 tokens
  Oversized Chunks (>2000): 1

  Warnings (1 total):
  - [TOKEN_BUDGET_EXCEEDED] Operation 'post_batch_transactions' (2450 tokens) exceeds budget of 2000
  ```
- **Exit Code**: `0`.

---

## Error Codes & Rejection Handling

| Condition | Exit Code | Stream | Message Pattern |
|---|---|---|---|
| **Swagger 2.0 Input** | `1` | `stderr` | `Error: Swagger 2.0 is not supported. SpecProbe requires OpenAPI 3.0 or 3.1.` |
| **File Not Found** | `1` | `stderr` | `Error: Specification file '<path>' does not exist.` |
| **Malformed YAML/JSON** | `1` | `stderr` | `Error: Failed to parse specification '<path>': <parser_details>` |
| **Operation ID Not Found** | `1` | `stderr` | `Error: Operation ID '<op>' not found in specification.` |
| **Unsupported External $ref** | `0` | `stderr` + chunk | `Warning: External reference '<ref>' is unsupported and was preserved without expansion.` |
