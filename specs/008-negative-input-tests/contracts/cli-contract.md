# CLI Contract: Negative Test Generation Options

**Feature**: `008-negative-input-tests`
**Date**: 2026-09-20
**Command**: `specprobe generate`

## 1. CLI Arguments & Options

```text
Usage: specprobe generate [OPTIONS] [CHUNKS_FILE]

  Generate executable test cases from OperationChunks using unified LiteLLM
  gateway, disk caching, and deterministic negative test generators.

Options:
  --negative-auth / --no-negative-auth
                                  Generate negative authentication test cases
                                  (401 missing credentials, 403 invalid
                                  credentials) for secured endpoints.
                                  [default: negative-auth]
  --not-found / --no-not-found    Generate negative 404 Not Found test cases
                                  for operations with path parameters.
                                  [default: not-found]
  --invalid-input / --no-invalid-input
                                  Generate negative 400 Bad Request test cases
                                  for operations with schema-constrained JSON
                                  request bodies.
                                  [default: invalid-input]
  -m, --model TEXT                LLM model name.
  --api-base TEXT                 Custom API base URL.
  --temperature FLOAT             Sampling temperature.
  --max-tokens INTEGER            Maximum completion tokens.
  --no-cache                      Bypass disk cache.
  --cache-dir PATH                Custom cache directory.
  -h, --help                      Show this message and exit.
```

---

## 2. Standard Output Contract (JSONL Stream)

Each emitted line on `stdout` is a validated JSON object conforming to `GeneratedTestCase`:

### 2.1 Sample 404 Output Record
```json
{
  "test_type": "negative_not_found",
  "operation_id": "findPetById",
  "description": "[404] Resource not found - findPetById",
  "request": {
    "method": "GET",
    "path": "/pets/{petId}",
    "path_params": {
      "petId": "999999"
    },
    "query_params": {},
    "headers": {
      "Accept": "application/json",
      "Authorization": "Bearer <token>"
    },
    "body": null
  },
  "response": {
    "status_code": 404,
    "headers": {
      "Content-Type": "application/json"
    },
    "schema_shape": null
  },
  "tags": [
    "pets",
    "negative",
    "404",
    "not_found"
  ],
  "security": [
    {
      "bearerAuth": []
    }
  ],
  "security_schemes": {
    "bearerAuth": {
      "type": "http",
      "scheme": "bearer"
    }
  }
}
```

### 2.2 Sample 400 Output Record
```json
{
  "test_type": "negative_invalid_input",
  "operation_id": "addPet",
  "description": "[400] Invalid input - addPet",
  "request": {
    "method": "POST",
    "path": "/pets",
    "path_params": {},
    "query_params": {},
    "headers": {
      "Content-Type": "application/json",
      "Accept": "application/json",
      "Authorization": "Bearer <token>"
    },
    "body": {
      "photoUrls": []
    }
  },
  "response": {
    "status_code": 400,
    "headers": {
      "Content-Type": "application/json"
    },
    "schema_shape": null
  },
  "tags": [
    "pets",
    "negative",
    "400",
    "invalid_input"
  ],
  "security": [
    {
      "bearerAuth": []
    }
  ],
  "security_schemes": {
    "bearerAuth": {
      "type": "http",
      "scheme": "bearer"
    }
  }
}
```
