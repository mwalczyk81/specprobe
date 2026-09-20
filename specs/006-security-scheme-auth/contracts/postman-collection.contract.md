# Contract: Postman Collection v2.1.0 Security Export

**Target Interface**: `specprobe export --format postman` (or `--format both`)  
**Output Format**: Postman Collection Schema v2.1.0 JSON  

---

## 1. Collection-Level Variable Declarations

All security schemes detected across exported test cases are parameterized into the collection's top-level `variable` array.

```json
{
  "info": {
    "_postman_id": "...",
    "name": "Petstore API",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "variable": [
    {
      "key": "baseUrl",
      "value": "http://localhost:8000",
      "type": "string"
    },
    {
      "key": "apiKeyAuth",
      "value": "<api_key>",
      "type": "string"
    },
    {
      "key": "bearerAuth",
      "value": "<token>",
      "type": "string"
    }
  ],
  "item": [...]
}
```

### Invariants:
1. `variable` items are sorted alphabetically by `key` (with `baseUrl` first).
2. Each unique sanitized scheme identifier appears at most once in `variable`.
3. Default placeholder values:
   - Bearer / OAuth2: `"<token>"`
   - Basic: `"<credentials>"`
   - API Key: `"<api_key>"`

---

## 2. Request-Level Credential Parameterization

### 2.1 HTTP Bearer / OAuth2 Scheme
```json
{
  "name": "Retrieve pet details",
  "request": {
    "method": "GET",
    "header": [
      {
        "key": "Authorization",
        "value": "Bearer {{bearerAuth}}",
        "type": "text"
      }
    ],
    "description": "Operation: get_pet_by_id\n\nSecurity: bearerAuth\nScopes: read:pets, write:pets"
  }
}
```

### 2.2 API Key in Header
```json
{
  "name": "Create a new pet",
  "request": {
    "method": "POST",
    "header": [
      {
        "key": "X-API-Key",
        "value": "{{apiKeyAuth}}",
        "type": "text"
      }
    ],
    "description": "Operation: create_pet\n\nSecurity: apiKeyAuth"
  }
}
```

### 2.3 API Key in Query Parameter
```json
{
  "name": "List all pets",
  "request": {
    "method": "GET",
    "url": {
      "raw": "{{baseUrl}}/pets?api_key={{queryApiKey}}",
      "host": ["{{baseUrl}}"],
      "path": ["pets"],
      "query": [
        {
          "key": "api_key",
          "value": "{{queryApiKey}}"
        }
      ]
    },
    "description": "Operation: list_pets\n\nSecurity: queryApiKey"
  }
}
```

### 2.4 Optional Security Annotation
```json
{
  "description": "Operation: get_public_or_private_pet\n\nSecurity: bearerAuth (optional)\nAlternatives: apiKeyAuth"
}
```
