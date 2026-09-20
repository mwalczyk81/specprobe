# Contract: VS Code REST Client (.http) Security Export

**Target Interface**: `specprobe export --format http` (or `--format both`)  
**Output Format**: RFC 7230 Plain-Text HTTP Document  

---

## 1. Top-Level File Variable Declarations

All security schemes detected across exported test cases are parameterized at the top of the file directly following `@baseUrl = ...`.

```http
@baseUrl = http://localhost:8000
@apiKeyAuth = <api_key>
@bearerAuth = <token>
@basicAuth = <credentials>
```

### Invariants:
1. File variables are sorted alphabetically by variable name following `@baseUrl`.
2. Each unique sanitized scheme identifier appears at most once.
3. If no operations require security, zero security file variables are emitted.

---

## 2. Request Block Serialization

### 2.1 Standard Bearer Auth Request Block
```http
###
# @name get_pet_by_id
# Operation: get_pet_by_id
# Description: Retrieve pet details for an existing pet ID
# Expected Status: 200
# Security: bearerAuth
# Expected Schema: type: object, properties: id, name
GET {{baseUrl}}/pets/1 HTTP/1.1
Authorization: Bearer {{bearerAuth}}
```

### 2.2 API Key in Header Request Block
```http
###
# @name create_pet
# Operation: create_pet
# Description: Create a new pet entry
# Expected Status: 201
# Security: apiKeyAuth
POST {{baseUrl}}/pets HTTP/1.1
Content-Type: application/json
X-API-Key: {{apiKeyAuth}}

{
  "name": "Rover",
  "tag": "dog"
}
```

### 2.3 API Key in Query Parameter Request Block
```http
###
# @name list_pets
# Operation: list_pets
# Description: Retrieve a paginated list of pets
# Expected Status: 200
# Security: queryApiKey
GET {{baseUrl}}/pets?api_key={{queryApiKey}}&limit=10 HTTP/1.1
Accept: application/json
```

### 2.4 Multiple Alternatives and Optional Security
```http
###
# @name search_pets
# Operation: search_pets
# Description: Search pet database with optional auth
# Expected Status: 200
# Security: bearerAuth (optional)
# Alternatives: apiKeyAuth
# Scopes: read:pets, write:pets
GET {{baseUrl}}/pets/search?q=dog HTTP/1.1
Authorization: Bearer {{bearerAuth}}
```
