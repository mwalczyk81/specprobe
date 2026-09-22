# Quickstart & Verification Guide: `specprobe mock`

**Feature**: `011-mock-server` | **Date**: 2026-09-22 | **Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/011-mock-server/spec.md)

---

## Overview

This guide provides runnable end-to-end scenarios to verify that `specprobe mock` correctly serves canned responses and enables exported Postman collections and VS Code REST Client files to execute and pass locally.

---

## Prerequisites

- SpecProbe development environment installed:
  ```powershell
  uv sync
  ```
- Sample test cases JSONL file available (e.g. [`tests/fixtures/generated_tests.jsonl`](file:///C:/Users/mwalc/source/repos/specprobe/tests/fixtures/generated_tests.jsonl)).

---

## Scenario 1: Basic File-Based Mock Server Execution

### 1. Start the Mock Server
In a terminal window, start the mock server using the sample Petstore test cases:

```powershell
uv run specprobe mock tests/fixtures/generated_tests.jsonl --port 8000
```

**Expected Startup Output:**
```text
╭───────────────────────── SpecProbe Mock Server ──────────────────────────╮
│ Running at: http://127.0.0.1:8000                                        │
│ Loaded: 4 positive routes from tests/fixtures/generated_tests.jsonl      │
╰──────────────────────────────────────────────────────────────────────────╯

Method   Path       Expected Status   Operation ID
──────   ────────   ───────────────   ────────────
GET      /pets      200 OK            listPets
POST     /pets      201 Created       createPets
GET      /pets/42   200 OK            showPetById
DELETE   /pets/42   204 No Content    delete_pets_pet_id

Press Ctrl+C to stop the server.
```

### 2. Send Test Requests
In a second terminal window, send requests to verify matching and canned responses:

```powershell
# 1. GET /pets (matches listPets, returns 200 array payload)
curl -i http://localhost:8000/pets?limit=10

# 2. POST /pets (matches createPets, returns 201 object payload)
curl -i -X POST http://localhost:8000/pets -H "Content-Type: application/json" -d '{"name":"Fido"}'

# 3. GET /pets/42 (matches showPetById with resolved param, returns 200)
curl -i http://localhost:8000/pets/42

# 4. DELETE /pets/42 (matches delete_pets_pet_id, returns 204 No Content with 0 bytes)
curl -i -X DELETE http://localhost:8000/pets/42
```

**Expected Results:**
- All 4 requests receive expected status codes (`200`, `201`, `200`, `204`).
- Content types match recorded headers (`Content-Type: application/json`).
- DELETE returns HTTP 204 with no body.
- Server console shows concise access log entries for each request:
  ```text
  [12:00:01] GET    /pets?limit=10  -> 200 OK (1.1ms)
  [12:00:02] POST   /pets           -> 201 Created (0.9ms)
  [12:00:03] GET    /pets/42        -> 200 OK (0.7ms)
  [12:00:04] DELETE /pets/42        -> 204 No Content (0.5ms)
  ```

---

## Scenario 2: End-to-End Exported Postman Collection Execution

### 1. Export Postman Collection & Environment
```powershell
uv run specprobe export tests/fixtures/generated_tests.jsonl --format postman -o ./tmp/quickstart_mock --env local=http://localhost:8000
```

### 2. Start Mock Server in Background or Separate Terminal
```powershell
uv run specprobe mock tests/fixtures/generated_tests.jsonl --port 8000
```

### 3. Run Postman Collection via Newman
```powershell
npx newman run ./tmp/quickstart_mock/collection.json -e ./tmp/quickstart_mock/local.postman_environment.json
```

**Expected Outcome:**
- 100% of test assertions pass:
  - `Status code is 200` / `Status code is 201` / `Status code is 204`
  - `Header Content-Type is present`
  - `Response matches JSON Schema` (verified against synthesized payload)
- Zero assertion failures.

---

## Scenario 3: Piped Standard Input Execution

Verify streaming via stdin using `-`:

```powershell
Get-Content tests/fixtures/generated_tests.jsonl | uv run specprobe mock - --port 8080
```

**Expected Outcome:**
- Mock server buffers the input stream until EOF, then binds port `8080` and displays loaded routes.

---

## Scenario 4: Diagnostic Handling for Unmatched Routes

Send requests that do not match registered endpoints:

```powershell
# Unmatched path:
curl -i http://localhost:8000/unknown/endpoint

# Unsupported method for registered path:
curl -i -X PATCH http://localhost:8000/pets
```

**Expected Outcome:**
- `/unknown/endpoint` returns HTTP `404 Not Found` with JSON body listing available routes.
- `PATCH /pets` returns HTTP `405 Method Not Allowed` with `Allow: GET, POST` header and diagnostic JSON.

---

## Scenario 5: Graceful Shutdown

In the terminal running `specprobe mock`, press `Ctrl+C` (or send `SIGINT`).

**Expected Outcome:**
- Server prints `Shutting down mock server...`
- Port `8000` is immediately released.
- Process exits with code `0`.
