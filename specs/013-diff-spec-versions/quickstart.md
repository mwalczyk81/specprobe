# Quickstart & Verification Guide: `specprobe diff`

**Feature Branch**: `013-diff-spec-versions`
**Date**: 2026-10-03
**Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/013-diff-spec-versions/spec.md)

This guide walks through practical scenarios to verify the `specprobe diff` command end-to-end using temporary OpenAPI test fixtures.

---

## Prerequisites

Ensure the virtual environment is activated and the CLI is installed in editable mode:

```bash
uv sync
```

---

## Scenario 1: Operation-Level Diff (Added & Removed Endpoints)

Verify that new endpoints are reported as non-breaking additions, and deleted endpoints are reported as breaking removals, keyed on method and path.

### 1. Create baseline spec (`v1.yaml`)
```yaml
openapi: 3.0.3
info:
  title: Pet Store API
  version: 1.0.0
paths:
  /pets:
    get:
      summary: List pets
      responses:
        '200':
          description: OK
  /pets/{id}:
    delete:
      summary: Delete pet
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        '204':
          description: No Content
```

### 2. Create candidate spec (`v2.yaml`)
```yaml
openapi: 3.0.3
info:
  title: Pet Store API
  version: 2.0.0
paths:
  /pets:
    get:
      summary: List pets
      responses:
        '200':
          description: OK
    post:
      summary: Create pet
      responses:
        '201':
          description: Created
```

### 3. Run diff command
```bash
specprobe diff v1.yaml v2.yaml --summary
```

### Expected Outcome
- `stdout` streams two JSONL records:
  1. `change_type: "operation_removed"`, `breaking: true`, `method: "DELETE"`, `path: "/pets/{id}"`
  2. `change_type: "operation_added"`, `breaking: false`, `method: "POST"`, `path: "/pets"`
- `stderr` displays a Rich summary table showing:
  - Total changes: 2
  - Breaking changes: 1
  - Operations added: 1
  - Operations removed: 1
- Process exit code is `1` (because an operation was removed).

---

## Scenario 2: Breaking Schema & 2xx Response Changes on Shared Endpoints

Verify detection of the five mechanical breaking change rules.

### 1. Create baseline spec (`schema_v1.yaml`)
```yaml
openapi: 3.0.3
info:
  title: Store API
  version: 1.0.0
paths:
  /items:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name]
              properties:
                name:
                  type: string
                price:
                  type: number
      responses:
        '200':
          description: Item retrieved
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  category:
                    type: string
                    enum: [electronics, home, garden]
        '404':
          description: Not found
```

### 2. Create candidate spec with 4 breaking changes and 1 non-breaking removal (`schema_v2.yaml`)
```yaml
openapi: 3.0.3
info:
  title: Store API
  version: 2.0.0
paths:
  /items:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name, price]   # 1. Price is newly required (breaking)
              properties:
                name:
                  type: string
                price:
                  type: integer          # 2. Type changed from number to integer (breaking)
      responses:
        '201':                           # 3. 200 was removed and swapped to 201 (response_status_removed, breaking)
          description: Created
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  # 4. category property was removed (breaking)
        # 404 response was removed (non-2xx removal, non-breaking, excluded from report)
```

### 3. Run diff command
```bash
specprobe diff schema_v1.yaml schema_v2.yaml --summary
```

### Expected Outcome
- `stdout` streams 4 breaking change records:
  1. `required_request_property_added`: `price` added to required request properties
  2. `type_changed`: `price` changed from `number` to `integer`
  3. `response_status_removed`: `200` removed from responses
  4. `response_property_removed`: `category` removed from response schema
- Note: The removal of the `404` status code is excluded from the report.
- Exit code is `1`.

---

## Scenario 3: Non-Breaking Changes, Parameter Renames, and Zero False Positives

Verify that cosmetic changes, description updates, parameter token renames, and non-breaking additions are excluded from diff output.

### 1. Create candidate spec with parameter rename and non-breaking edits (`non_breaking_v2.yaml`)
```yaml
openapi: 3.0.3
info:
  title: Store API (Updated Description)
  description: A completely rewritten description
  version: 1.1.0
paths:
  /items:
    post:
      summary: Brand new summary text
      description: Detailed description of creating an item
      operationId: createNewItemAlternativeId  # Renamed operationId (no false removal)
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name]
              properties:
                name:
                  type: string
                price:
                  type: number
                notes:                         # Optional property added (non-breaking)
                  type: string
      responses:
        '200':
          description: Item retrieved successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  category:
                    type: string
                    enum: [electronics, home, garden, apparel]  # Enum value added (non-breaking)
                  createdAt:                   # Response property added (non-breaking)
                    type: string
        '404':
          description: Item not found
```

### 2. Run diff against baseline
```bash
specprobe diff schema_v1.yaml non_breaking_v2.yaml --summary
```

### Expected Outcome
- `stdout` emits zero lines.
- Exit code is `0`.
- Summary table displays `0 Total Changes, 0 Breaking Changes`.

---

## Scenario 4: Error Handling & Invalid Files

### Run against nonexistent file
```bash
specprobe diff nonexistent.yaml schema_v1.yaml
```

### Expected Outcome
- `stderr` outputs: `Error: Specification file 'nonexistent.yaml' does not exist.`
- Process exits with code `2`.
