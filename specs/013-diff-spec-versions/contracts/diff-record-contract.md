# Contract: `DiffChangeRecord` JSONL Output Schema

**Format**: JSON Lines (`JSONL`)
**Target Stream**: `stdout`
**Feature Branch**: `013-diff-spec-versions`
**Date**: 2026-10-03
**Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/013-diff-spec-versions/spec.md)

---

## 1. JSON Schema Definition (Draft 7)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "DiffChangeRecord",
  "description": "An individual structural change detected between two OpenAPI specification versions.",
  "type": "object",
  "required": [
    "change_type",
    "breaking",
    "location",
    "description"
  ],
  "properties": {
    "change_type": {
      "type": "string",
      "enum": [
        "operation_added",
        "operation_removed",
        "required_request_property_added",
        "response_property_removed",
        "response_status_removed",
        "type_changed",
        "enum_value_removed"
      ]
    },
    "breaking": {
      "type": "boolean"
    },
    "method": {
      "type": ["string", "null"]
    },
    "path": {
      "type": ["string", "null"]
    },
    "location": {
      "type": "string"
    },
    "description": {
      "type": "string"
    },
    "old_value": {},
    "new_value": {}
  },
  "additionalProperties": false
}
```

---

## 2. Sample Payloads

### Operation Added (Non-Breaking)
```json
{
  "change_type": "operation_added",
  "breaking": false,
  "method": "POST",
  "path": "/api/v1/pets",
  "location": "paths['/api/v1/pets'].post",
  "description": "Operation 'POST /api/v1/pets' was added in the new specification.",
  "old_value": null,
  "new_value": {"summary": "Create a pet"}
}
```

### Operation Removed (Breaking)
```json
{
  "change_type": "operation_removed",
  "breaking": true,
  "method": "DELETE",
  "path": "/api/v1/pets/{id}",
  "location": "paths['/api/v1/pets/{id}'].delete",
  "description": "Operation 'DELETE /api/v1/pets/{id}' was removed in the new specification.",
  "old_value": {"summary": "Delete a pet"},
  "new_value": null
}
```

### Required Request Property Added (Breaking)
```json
{
  "change_type": "required_request_property_added",
  "breaking": true,
  "method": "POST",
  "path": "/api/v1/pets",
  "location": "requestBody.content['application/json'].schema.required",
  "description": "New required property 'tag' was added to request body schema.",
  "old_value": ["name"],
  "new_value": ["name", "tag"]
}
```

### Response Property Removed (Breaking)
```json
{
  "change_type": "response_property_removed",
  "breaking": true,
  "method": "GET",
  "path": "/api/v1/pets/{id}",
  "location": "responses['200'].content['application/json'].schema.properties.age",
  "description": "Property 'age' was removed from response schema for status code '200'.",
  "old_value": {"type": "integer"},
  "new_value": null
}
```

### Response Status Removed (Breaking - 2xx Only)
```json
{
  "change_type": "response_status_removed",
  "breaking": true,
  "method": "GET",
  "path": "/api/v1/pets/{id}",
  "location": "responses['200']",
  "description": "Success response status code '200' was removed from operation.",
  "old_value": {"description": "Pet found"},
  "new_value": null
}
```

### Field Type Changed (Breaking)
```json
{
  "change_type": "type_changed",
  "breaking": true,
  "method": "GET",
  "path": "/api/v1/pets/{id}",
  "location": "parameters[in='path',name='id'].schema.type",
  "description": "Type of parameter 'id' changed from 'string' to 'integer'.",
  "old_value": "string",
  "new_value": "integer"
}
```

### Enum Value Removed (Breaking)
```json
{
  "change_type": "enum_value_removed",
  "breaking": true,
  "method": "GET",
  "path": "/api/v1/pets",
  "location": "parameters[in='query',name='status'].schema.enum",
  "description": "Enum value 'pending' was removed from query parameter 'status'.",
  "old_value": ["available", "pending", "sold"],
  "new_value": ["available", "sold"]
}
```
