# Exporter Artifact Contract: 404 & 400 Sibling Representation

**Feature**: `008-negative-input-tests`
**Date**: 2026-09-20
**Command**: `specprobe export`

## 1. Postman Collection v2.1.0 Contract

### 1.1 Item Naming & Folder Organization
- Positive and negative sibling test cases for an operation are grouped within the operation's tag folder.
- Item `name`:
  - 404 Not Found: `[404] Resource not found - {operation_id}` (or `[404] {description}`)
  - 400 Bad Request: `[400] Invalid input - {operation_id}` (or `[400] {description}`)

### 1.2 Status Assertion Script
In the `event` test script:
- 404:
  ```javascript
  pm.test("Status code is 404", function () {
      pm.response.to.have.status(404);
  });
  ```
- 400:
  ```javascript
  pm.test("Status code is 400", function () {
      pm.response.to.have.status(400);
  });
  ```

### 1.3 Credentials & Parameters
- Security headers retain collection variable parameterization:
  ```json
  {
    "key": "Authorization",
    "value": "Bearer {{bearerAuth}}"
  }
  ```
- Collection variables (`{{bearerAuth}}`, `{{apiKey}}`, etc.) are declared at the root of the collection document.

---

## 2. VS Code REST Client (`.http`) Contract

### 2.1 Request Block Annotations
```http
###
# @name findPetById_404
# Operation: findPetById
# Description: [404] Resource not found - findPetById
# Expected Status: 404
GET {{baseUrl}}/pets/999999
Accept: application/json
Authorization: Bearer {{bearerAuth}}

###
# @name addPet_400
# Operation: addPet
# Description: [400] Invalid input - addPet
# Expected Status: 400
POST {{baseUrl}}/pets
Content-Type: application/json
Accept: application/json
Authorization: Bearer {{bearerAuth}}

{
  "photoUrls": []
}
```

### 2.2 Top-level Variables
File-level variables retain real placeholders:
```http
@baseUrl = http://localhost:8000
@bearerAuth = <token>
```
