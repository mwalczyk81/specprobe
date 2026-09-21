# Contract: GeneratedTestCase JSONL Security Format

**Target Interface**: `specprobe generate` output / `specprobe export` input
**Protocol**: JSON Lines (JSONL)

---

## Record Schema

Each line emitted by `specprobe generate` or ingested by `specprobe export` is a JSON object conforming to `GeneratedTestCase`:

```json
{
  "operation_id": "get_pet_by_id",
  "description": "Retrieve pet details for an existing pet ID",
  "request": {
    "method": "GET",
    "path": "/pets/{petId}",
    "path_params": {
      "petId": 1
    },
    "query_params": {},
    "headers": {
      "Authorization": "Bearer <token>"
    },
    "body": null
  },
  "response": {
    "status_code": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "schema_shape": {
      "type": "object",
      "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"}
      },
      "required": ["id", "name"]
    }
  },
  "tags": ["pets"],
  "security": [
    {
      "bearerAuth": []
    },
    {
      "apiKeyAuth": []
    }
  ],
  "security_schemes": {
    "bearerAuth": {
      "type": "http",
      "scheme": "bearer",
      "bearerFormat": "JWT"
    },
    "apiKeyAuth": {
      "type": "apiKey",
      "name": "X-API-Key",
      "in": "header"
    }
  }
}
```

## Field Specifications

- `security` (`list[dict[str, list[str]]]`, optional, default `[]`):
  List of security requirement objects as defined in OpenAPI. An empty dictionary `{}` within the list indicates optional security.
- `security_schemes` (`dict[str, object]`, optional, default `{}`):
  Dictionary mapping scheme identifiers to their OpenAPI `components.securitySchemes` definitions.
- `request.headers` / `request.query_params`:
  Contains the concrete placeholder credential (e.g. `"Authorization": "Bearer <token>"` or `"X-API-Key": "<api_key>"`).
