# HTTP Server Contract: Mock Server Protocol & Response Semantics

**Feature**: `011-mock-server` | **Date**: 2026-09-22 | **Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/011-mock-server/spec.md)

---

## 1. Request Matching Rules

Incoming HTTP requests are matched against the in-memory route registry using the following deterministic evaluation:

1. **Path Extraction & Normalization**:
   - Query parameters are stripped (e.g., `/pets?limit=10&page=1` becomes `/pets`).
   - Percent-encoded characters in path segments are decoded (e.g., `/users/john%20doe` becomes `/users/john doe`).
   - Trailing slashes are stripped unless the path is the root `/` (e.g., `/pets/` becomes `/pets`).
2. **Method Normalization**:
   - HTTP method is evaluated case-insensitively and normalized to uppercase (`GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `OPTIONS`, `HEAD`).
3. **Lookup**:
   - The route table is queried for `(normalized_method, normalized_path)`.
   - Incoming request headers, authorization tokens, query strings, and request body payloads are **ignored**.

---

## 2. Response Semantics

### 2.1. Matched Route Success

When a request matches a registered `MockRoute`:

- **Status Code**: Emits `MockRoute.response.status_code` (e.g. `200`, `201`, `204`).
- **Response Headers**:
  - Emits all headers defined in `MockRoute.response.headers` (e.g. `Content-Type: application/json`).
  - Emits `Content-Length: <len>` automatically based on body bytes length.
  - Emits `Connection: close` (or `keep-alive` per client header).
- **Response Body**:
  - For HTTP 204 No Content: returns zero bytes (`b""`).
  - For 2xx responses with JSON content type: returns pre-rendered JSON bytes synthesized from `schema_shape` or concrete `response.body`.

### 2.2. Unmatched Route (HTTP 404 Not Found)

When no registered route matches the requested path for *any* HTTP method:

- **Status Code**: `404`
- **Response Headers**: `Content-Type: application/json`
- **Response Body**:
  ```json
  {
    "error": "Not Found",
    "message": "No mock route registered for path '/unknown'",
    "requested": {
      "method": "GET",
      "path": "/unknown"
    },
    "available_routes": [
      {
        "method": "GET",
        "path": "/pets",
        "operation_id": "listPets"
      },
      {
        "method": "POST",
        "path": "/pets",
        "operation_id": "createPets"
      },
      {
        "method": "GET",
        "path": "/pets/42",
        "operation_id": "showPetById"
      }
    ]
  }
  ```

### 2.3. Method Not Allowed (HTTP 405)

When the requested path exists in the route registry, but the requested HTTP method is not registered for that path:

- **Status Code**: `405`
- **Response Headers**:
  - `Content-Type: application/json`
  - `Allow: <comma-separated list of allowed methods for this path>` (e.g., `Allow: GET, POST`)
- **Response Body**:
  ```json
  {
    "error": "Method Not Allowed",
    "message": "Method 'DELETE' is not supported for path '/pets'",
    "requested": {
      "method": "DELETE",
      "path": "/pets"
    },
    "allowed_methods": ["GET", "POST"]
  }
  ```
