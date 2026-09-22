# CLI Contract: `specprobe mock`

**Feature**: `011-mock-server` | **Date**: 2026-09-22 | **Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/011-mock-server/spec.md)

---

## Command Synopsis

```bash
specprobe mock [OPTIONS] TEST_CASES_FILE
```

## Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `TEST_CASES_FILE` | Path or `"-"` | **Yes** | Path to the `GeneratedTestCase` JSONL file, or `"-"` to stream test cases via standard input. |

## Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--port` | `-p` | Integer (1–65535) | `8000` | Port to bind the HTTP mock server to. |
| `--host` | `-h` | String | `127.0.0.1` | Network interface / host to bind to. |
| `--help` | | Flag | | Show help message and exit. |

---

## Exit Codes

| Exit Code | Meaning | Description |
|-----------|---------|-------------|
| `0` | Success | Normal shutdown triggered by user interrupt (SIGINT / Ctrl+C). |
| `1` | Error | Unrecoverable error (e.g. file not found, empty file, malformed JSONL, port unavailable). |
| `2` | Usage Error | Click argument parsing error (e.g. missing required `TEST_CASES_FILE` argument). |

---

## Console Output Streams

### Standard Output (`stdout`)
Used for interactive terminal feedback during foreground execution:
1. **Startup Banner**: Printed via `rich.console`, showing the server URL, port, total routes registered, and a formatted route table:
   ```text
   ╭───────────────────────── SpecProbe Mock Server ──────────────────────────╮
   │ Running at: http://127.0.0.1:8000                                        │
   │ Loaded: 4 positive routes from test_cases.jsonl                          │
   ╰──────────────────────────────────────────────────────────────────────────╯

   Method   Path       Expected Status   Operation ID
   ──────   ────────   ───────────────   ────────────
   GET      /pets      200 OK            listPets
   POST     /pets      201 Created       createPets
   GET      /pets/42   200 OK            showPetById
   DELETE   /pets/42   204 No Content    delete_pets_pet_id

   Press Ctrl+C to stop the server.
   ```
2. **Access Log Lines**: Concise single-line log for each request:
   ```text
   [12:00:01] GET    /pets?limit=10  -> 200 OK (1.2ms)
   [12:00:02] POST   /pets           -> 201 Created (1.5ms)
   [12:00:03] GET    /pets/42        -> 200 OK (0.8ms)
   [12:00:04] GET    /unknown        -> 404 Not Found (0.4ms) [UNMATCHED]
   ```

### Standard Error (`stderr`)
Used exclusively for diagnostic error messages when startup fails:
```text
Error: Failed to bind port 8000 on 127.0.0.1: [Errno 98] Address already in use.
```
```text
Error: Test cases file './missing.jsonl' does not exist.
```
```text
Error: No valid positive test cases found in './empty.jsonl'.
```
