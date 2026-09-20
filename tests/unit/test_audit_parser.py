"""Unit tests for deterministic Postman Collection and REST Client (.http) artifact parsers."""

from pathlib import Path

from specprobe.audit.parser import (
    parse_artifact,
    parse_http_document,
    parse_postman_collection,
)

FIXTURES_DIR = Path("tests/fixtures")
POSTMAN_FIXTURE = FIXTURES_DIR / "audit_postman_collection.json"
HTTP_FIXTURE = FIXTURES_DIR / "audit_sample_requests.http"


def test_parse_postman_collection_fixture() -> None:
    """Verify parsing of sample Postman collection fixture with folder traversal."""
    content = POSTMAN_FIXTURE.read_text(encoding="utf-8")
    items = parse_postman_collection(content)

    assert len(items) == 3

    # Item 1: List all pets
    item0 = items[0]
    assert item0.name == "List all pets"
    assert item0.method == "GET"
    assert item0.path == "/pets"
    assert item0.expected_status == 200
    assert item0.has_property_assertions is True
    assert item0.has_schema_assertion is False

    # Item 2: Info for a specific pet
    item1 = items[1]
    assert item1.name == "Info for a specific pet"
    assert item1.method == "GET"
    assert item1.path == "/pets/1"
    assert item1.expected_status == 200
    assert item1.has_property_assertions is False
    assert item1.has_schema_assertion is False

    # Item 3: Orphan request
    item2 = items[2]
    assert item2.name == "Orphan request not in spec"
    assert item2.method == "GET"
    assert item2.path == "/orphan/test"
    assert item2.expected_status == 200


def test_parse_postman_with_json_schema_assertions() -> None:
    """Verify detection of pm.response.to.have.jsonSchema assertions."""
    postman_raw = {
        "info": {"name": "Test"},
        "item": [
            {
                "name": "Schema Check Request",
                "request": {
                    "method": "POST",
                    "url": "http://localhost:8000/pets",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": {"mode": "raw", "raw": '{"name": "Spot"}'},
                },
                "event": [
                    {
                        "listen": "test",
                        "script": {
                            "type": "text/javascript",
                            "exec": [
                                'pm.test("Status code is 201", function () {',
                                "    pm.response.to.have.status(201);",
                                "});",
                                "pm.test('Valid Schema', function () {",
                                "    pm.response.to.have.jsonSchema(schema);",
                                "});",
                            ],
                        },
                    }
                ],
            }
        ],
    }
    items = parse_postman_collection(postman_raw)
    assert len(items) == 1
    assert items[0].method == "POST"
    assert items[0].path == "/pets"
    assert items[0].expected_status == 201
    assert items[0].has_body is True
    assert items[0].has_schema_assertion is True


def test_parse_http_document_fixture() -> None:
    """Verify parsing of RFC 7230 REST Client (.http) file fixture."""
    content = HTTP_FIXTURE.read_text(encoding="utf-8")
    items = parse_http_document(content)

    assert len(items) == 2

    # Item 0: listPets
    item0 = items[0]
    assert item0.name == "listPets"
    assert item0.method == "GET"
    assert item0.path == "/pets"
    assert item0.expected_status == 200
    assert item0.headers.get("Accept") == "application/json"

    # Item 1: showPetById
    item1 = items[1]
    assert item1.name == "showPetById"
    assert item1.method == "GET"
    assert item1.path == "/pets/42"
    assert item1.expected_status == 200


def test_parse_http_document_with_schema_comment() -> None:
    """Verify detection of # Expected Schema: metadata comments in .http files."""
    http_text = """@baseUrl = http://localhost:8000

###
# @name listPets
# Expected Status: 200
# Expected Schema: array of object (properties: id, name)
GET {{baseUrl}}/pets?limit=10 HTTP/1.1
"""
    items = parse_http_document(http_text)
    assert len(items) == 1
    assert items[0].method == "GET"
    assert items[0].path == "/pets"
    assert items[0].query_params == ["limit"]
    assert items[0].expected_status == 200
    assert items[0].has_schema_assertion is True


def test_parse_artifact_auto_detection() -> None:
    """Verify parse_artifact automatically determines format by extension and content."""
    items_postman = parse_artifact(str(POSTMAN_FIXTURE))
    assert len(items_postman) == 3

    items_http = parse_artifact(str(HTTP_FIXTURE))
    assert len(items_http) == 2

    # Empty string should return empty list
    assert parse_artifact("") == []
