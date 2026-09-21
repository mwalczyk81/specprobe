"""Unit tests for Postman Collection v2.1.0 serializer."""

import json
import uuid

import pytest
from hypothesis import given
from hypothesis import strategies as st

from specprobe.exporter.postman import generate_postman_collection
from specprobe.exporter.utils import extract_schema_properties
from specprobe.generator.models import GeneratedTestCase, RequestFixture, ResponseAssertion


@pytest.fixture
def sample_test_case() -> GeneratedTestCase:
    """Return a representative GeneratedTestCase for testing Postman serialization."""
    return GeneratedTestCase(
        operation_id="showPetById",
        description="Retrieve specific pet by ID",
        request=RequestFixture(
            method="GET",
            path="/pets/{petId}",
            path_params={"petId": "42"},
            query_params={},
            headers={"Accept": "application/json"},
            body=None,
        ),
        response=ResponseAssertion(
            status_code=200,
            headers={"Content-Type": "application/json"},
            schema_shape={
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "tag": {"type": "string"},
                },
            },
        ),
        tags=["pets", "store"],
    )


def test_postman_id_determinism(sample_test_case: GeneratedTestCase) -> None:
    """Verify that _postman_id is a deterministic UUIDv5 based on collection name."""
    col1 = generate_postman_collection([sample_test_case], collection_name="Petstore API")
    col2 = generate_postman_collection([sample_test_case], collection_name="Petstore API")

    id1 = col1["info"]["_postman_id"]
    id2 = col2["info"]["_postman_id"]

    assert id1 == id2
    # Verify it matches expected UUIDv5
    expected_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, "specprobe:Petstore API"))
    assert id1 == expected_uuid

    # Different collection name must produce different UUIDv5
    col_other = generate_postman_collection([sample_test_case], collection_name="Other API")
    assert col_other["info"]["_postman_id"] != id1


def test_base_url_variable(sample_test_case: GeneratedTestCase) -> None:
    """Verify baseUrl variable declaration in Postman collection."""
    # Default base_url
    col_default = generate_postman_collection([sample_test_case])
    variables = col_default.get("variable", [])
    assert len(variables) == 1
    assert variables[0]["key"] == "baseUrl"
    assert variables[0]["value"] == "http://localhost:8000"
    assert variables[0]["type"] == "string"

    # Custom base_url
    col_custom = generate_postman_collection(
        [sample_test_case], base_url="https://api.petstore.io/v2"
    )
    assert col_custom["variable"][0]["value"] == "https://api.petstore.io/v2"


def test_primary_tag_folder_grouping(sample_test_case: GeneratedTestCase) -> None:
    """Verify grouping into primary tag folder (tags[0]) without duplication."""
    tc2 = GeneratedTestCase(
        operation_id="listPets",
        description="List all pets",
        request=RequestFixture(method="GET", path="/pets"),
        response=ResponseAssertion(status_code=200),
        tags=["pets"],
    )
    tc3 = GeneratedTestCase(
        operation_id="getOrder",
        description="Get store order",
        request=RequestFixture(method="GET", path="/store/order/1"),
        response=ResponseAssertion(status_code=200),
        tags=["store"],
    )

    # sample_test_case has tags=["pets", "store"]
    collection = generate_postman_collection([sample_test_case, tc2, tc3])
    items = collection["item"]

    # There should be 2 folders: "pets" and "store"
    folder_names = [folder["name"] for folder in items]
    assert folder_names == ["pets", "store"]

    # "pets" folder should contain sample_test_case and tc2
    pets_folder = items[0]
    assert pets_folder["name"] == "pets"
    assert len(pets_folder["item"]) == 2
    assert pets_folder["item"][0]["name"] == "Retrieve specific pet by ID"
    assert pets_folder["item"][1]["name"] == "List all pets"

    # "store" folder should contain only tc3 (sample_test_case is NOT duplicated here)
    store_folder = items[1]
    assert store_folder["name"] == "store"
    assert len(store_folder["item"]) == 1
    assert store_folder["item"][0]["name"] == "Get store order"


def test_untagged_test_case_handling() -> None:
    """Untagged test cases must be placed at the collection root without error."""
    tc_untagged = GeneratedTestCase(
        operation_id="healthCheck",
        description="Check server health",
        request=RequestFixture(method="GET", path="/health"),
        response=ResponseAssertion(status_code=200),
        tags=[],
    )
    tc_tagged = GeneratedTestCase(
        operation_id="listPets",
        description="List all pets",
        request=RequestFixture(method="GET", path="/pets"),
        response=ResponseAssertion(status_code=200),
        tags=["pets"],
    )

    collection = generate_postman_collection([tc_tagged, tc_untagged])
    items = collection["item"]

    # items should have folder "pets" and direct request item "Check server health"
    assert len(items) == 2
    assert items[0]["name"] == "pets"
    assert "item" in items[0]  # it's a folder
    assert items[1]["name"] == "Check server health"
    assert "request" in items[1]  # it's a direct item


def test_path_substitution_and_url_encoding() -> None:
    """Path parameters must be substituted and URL-encoded per RFC 3986."""
    tc = GeneratedTestCase(
        operation_id="findPet",
        description="Find pet with special characters",
        request=RequestFixture(
            method="GET",
            path="/pets/{category}/{petName}",
            path_params={"category": "dogs & cats", "petName": "fido/fluffy"},
            query_params={"limit": 5},
        ),
        response=ResponseAssertion(status_code=200),
        tags=["pets"],
    )

    collection = generate_postman_collection([tc])
    req = collection["item"][0]["item"][0]["request"]

    # Verify raw URL template
    expected_path = "/pets/dogs%20%26%20cats/fido%2Ffluffy"
    assert req["url"]["raw"] == f"{{{{baseUrl}}}}{expected_path}?limit=5"
    assert req["url"]["host"] == ["{{baseUrl}}"]
    assert req["url"]["path"] == ["pets", "dogs%20%26%20cats", "fido%2Ffluffy"]
    assert req["url"]["query"] == [{"key": "limit", "value": "5"}]


def test_headers_and_body_payload() -> None:
    """Request headers and JSON body payloads must be correctly formatted."""
    tc = GeneratedTestCase(
        operation_id="createPet",
        description="Create a pet",
        request=RequestFixture(
            method="POST",
            path="/pets",
            headers={"Content-Type": "application/json", "X-Custom-Header": "test-123"},
            body={"name": "Rex", "age": 3},
        ),
        response=ResponseAssertion(status_code=201),
        tags=["pets"],
    )

    collection = generate_postman_collection([tc])
    req = collection["item"][0]["item"][0]["request"]

    assert req["method"] == "POST"

    # Verify headers
    headers = req["header"]
    assert len(headers) == 2
    header_map = {h["key"]: h["value"] for h in headers}
    assert header_map["Content-Type"] == "application/json"
    assert header_map["X-Custom-Header"] == "test-123"

    # Verify body
    body = req["body"]
    assert body["mode"] == "raw"
    assert body["options"]["raw"]["language"] == "json"
    parsed_body = json.loads(body["raw"])
    assert parsed_body == {"name": "Rex", "age": 3}


def test_empty_body_and_headers() -> None:
    """Requests without body or headers should omit body and have empty header list."""
    tc = GeneratedTestCase(
        operation_id="deletePet",
        description="Delete a pet",
        request=RequestFixture(
            method="DELETE",
            path="/pets/{petId}",
            path_params={"petId": "99"},
            headers={},
            body=None,
        ),
        response=ResponseAssertion(status_code=204),
        tags=[],
    )

    collection = generate_postman_collection([tc])
    req = collection["item"][0]["request"]

    assert "body" not in req
    assert req["header"] == []


def test_pm_test_assertions(sample_test_case: GeneratedTestCase) -> None:
    """Verify status code, header, and property assertions in pm.test scripts."""
    collection = generate_postman_collection([sample_test_case])
    item = collection["item"][0]["item"][0]

    event = item["event"][0]
    assert event["listen"] == "test"
    script = event["script"]
    assert script["type"] == "text/javascript"

    exec_lines = script["exec"]
    script_text = "\n".join(exec_lines)

    # 1. Status code assertion
    assert 'pm.test("Status code is 200", function () {' in script_text
    assert "pm.response.to.have.status(200);" in script_text

    # 2. Header assertion
    assert 'pm.test("Header Content-Type is present", function () {' in script_text
    assert 'pm.response.to.have.header("Content-Type");' in script_text

    # 3. JSON Schema assertions
    assert 'pm.test("Response matches JSON Schema", function () {' in script_text
    assert "var schema = {" in script_text
    assert "pm.response.to.have.jsonSchema(schema);" in script_text


def test_operation_id_traceability(sample_test_case: GeneratedTestCase) -> None:
    """Verify operation_id is preserved in request description."""
    collection = generate_postman_collection([sample_test_case])
    req = collection["item"][0]["item"][0]["request"]

    assert "Operation: showPetById" in req["description"]
    assert "Retrieve specific pet by ID" in req["description"]


def test_empty_test_cases() -> None:
    """Empty test case list should produce a valid empty collection."""
    collection = generate_postman_collection([], collection_name="Empty Collection")

    assert collection["info"]["name"] == "Empty Collection"
    assert collection["info"]["schema"] == (
        "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    )
    assert collection["variable"][0]["key"] == "baseUrl"
    assert collection["item"] == []


def test_extract_schema_properties_helper() -> None:
    """Verify schema property extraction across diverse schema structures."""
    # List of properties in dict
    assert extract_schema_properties({"type": "object", "properties": ["id", "name"]}) == [
        "id",
        "name",
    ]

    # Dict of properties in dict
    assert extract_schema_properties(
        {"type": "object", "properties": {"id": {"type": "integer"}, "name": {"type": "string"}}}
    ) == ["id", "name"]

    # Array schema with items properties
    assert extract_schema_properties(
        {"type": "array", "items": {"properties": ["code", "message"]}}
    ) == ["code", "message"]

    # Direct list of property strings
    assert extract_schema_properties(["id", "name"]) == ["id", "name"]

    # None or empty
    assert extract_schema_properties(None) == []
    assert extract_schema_properties({}) == []

    # Unresolved $ref pointer should yield no property assertions
    assert extract_schema_properties({"$ref": "#/components/schemas/Pet"}) == []
    assert (
        extract_schema_properties({"$ref": "#/components/schemas/Pet", "description": "Pet"}) == []
    )
    assert (
        extract_schema_properties({"type": "array", "items": {"$ref": "#/components/schemas/Pet"}})
        == []
    )


def test_none_schema_shape_omits_json_schema_assertions() -> None:
    """A test case with schema_shape=None must not emit jsonSchema assertions."""
    tc = GeneratedTestCase(
        operation_id="getPet",
        description="Get pet by ID",
        request=RequestFixture(
            method="GET",
            path="/pets/1",
            path_params={},
            query_params={},
            headers={"Accept": "application/json"},
            body=None,
        ),
        response=ResponseAssertion(
            status_code=204,
            headers={"Content-Type": "application/json"},
            schema_shape=None,
        ),
        tags=["pets"],
    )
    collection = generate_postman_collection([tc])
    script = collection["item"][0]["item"][0]["event"][0]["script"]
    script_text = "\n".join(script["exec"])

    # Must retain status code and header assertions
    assert 'pm.test("Status code is 204", function () {' in script_text
    assert 'pm.test("Header Content-Type is present", function () {' in script_text

    # Must NOT emit jsonSchema assertion block
    assert "Response matches JSON Schema" not in script_text
    assert "jsonSchema" not in script_text


@st.composite
def generated_test_case_strategy(draw: st.DrawFn) -> GeneratedTestCase:
    """Generate arbitrary GeneratedTestCase instances with varying fixtures and assertions."""
    op_id = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
        )
    )
    description = draw(st.text(min_size=1, max_size=50))
    tags = draw(
        st.lists(
            st.text(
                min_size=1,
                max_size=15,
                alphabet=st.characters(whitelist_categories=("L", "N")),
            ),
            max_size=4,
        )
    )
    method = draw(st.sampled_from(["GET", "POST", "PUT", "DELETE", "PATCH"]))
    path = draw(st.sampled_from(["/items", "/items/{id}", "/users/{userId}/orders/{orderId}", "/"]))
    path_params = draw(
        st.dictionaries(
            keys=st.sampled_from(["id", "userId", "orderId"]),
            values=st.text(min_size=1, max_size=10),
            max_size=2,
        )
    )
    query_params = draw(
        st.dictionaries(
            keys=st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"),
            values=st.text(max_size=10),
            max_size=3,
        )
    )
    headers = draw(
        st.dictionaries(
            keys=st.sampled_from(["Content-Type", "Accept", "X-Api-Key", "Authorization"]),
            values=st.text(min_size=1, max_size=20),
            max_size=3,
        )
    )
    body = draw(
        st.one_of(
            st.none(),
            st.dictionaries(
                keys=st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"),
                values=st.text(max_size=20),
                max_size=3,
            ),
        )
    )
    test_type = draw(
        st.sampled_from(
            [
                "positive",
                "negative_auth_missing",
                "negative_auth_invalid",
                "negative_not_found",
                "negative_invalid_input",
            ]
        )
    )
    if test_type == "negative_auth_missing":
        status_code = 401
    elif test_type == "negative_auth_invalid":
        status_code = 403
    elif test_type == "negative_not_found":
        status_code = 404
    elif test_type == "negative_invalid_input":
        status_code = 400
    else:
        status_code = draw(st.integers(min_value=200, max_value=299))
    resp_headers = draw(
        st.dictionaries(
            keys=st.sampled_from(["Content-Type", "ETag", "Location"]),
            values=st.text(min_size=1, max_size=20),
            max_size=2,
        )
    )
    schema_shape = draw(
        st.one_of(
            st.none(),
            st.fixed_dictionaries(
                {
                    "type": st.just("object"),
                    "properties": st.dictionaries(
                        keys=st.text(
                            min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"
                        ),
                        values=st.fixed_dictionaries({"type": st.just("string")}),
                        max_size=4,
                    ),
                }
            ),
        )
    )

    return GeneratedTestCase(
        test_type=test_type,
        operation_id=op_id,
        description=description,
        request=RequestFixture(
            method=method,
            path=path,
            path_params=path_params,
            query_params=query_params,
            headers=headers,
            body=body,
        ),
        response=ResponseAssertion(
            status_code=status_code,
            headers=resp_headers,
            schema_shape=schema_shape,
        ),
        tags=tags,
        security=draw(
            st.sampled_from(
                [
                    [],
                    [{"bearerAuth": []}],
                    [{"apiKeyAuth": []}],
                    [{"bearerAuth": []}, {}],
                    [{"oauth2Auth": ["read:pets", "write:pets"]}],
                    [{"apiKeyAuth": [], "appIdAuth": []}],
                ]
            )
        ),
        security_schemes=draw(
            st.sampled_from(
                [
                    {},
                    {
                        "bearerAuth": {"type": "http", "scheme": "bearer"},
                        "apiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
                        "oauth2Auth": {"type": "oauth2"},
                        "appIdAuth": {"type": "apiKey", "in": "header", "name": "X-App-Id"},
                    },
                ]
            )
        ),
    )


@given(
    test_cases=st.lists(generated_test_case_strategy(), min_size=0, max_size=6),
    collection_name=st.one_of(st.none(), st.text(min_size=1, max_size=30)),
    base_url=st.sampled_from(
        ["http://localhost:8000", "https://api.example.com", "http://127.0.0.1:5000/v1"]
    ),
)
def test_hypothesis_postman_export_determinism(
    test_cases: list[GeneratedTestCase],
    collection_name: str | None,
    base_url: str,
) -> None:
    """Constitution Principle II property test:
    Assert calling generate_postman_collection twice on the same input produces
    byte-identical JSON serialization across arbitrary test case batches.
    """
    col1 = generate_postman_collection(
        test_cases, collection_name=collection_name, base_url=base_url
    )
    col2 = generate_postman_collection(
        test_cases, collection_name=collection_name, base_url=base_url
    )

    json1 = json.dumps(col1, indent=2, ensure_ascii=False)
    json2 = json.dumps(col2, indent=2, ensure_ascii=False)

    assert json1 == json2
    assert col1 == col2
