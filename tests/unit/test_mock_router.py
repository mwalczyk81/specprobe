"""Unit tests for MockRouter route registration, matching, and diagnostics."""

import json
import warnings

from specprobe.generator.models import GeneratedTestCase
from specprobe.mock.router import (
    MockRouter,
    build_method_not_allowed_response,
    build_not_found_response,
)


def _test_case(**overrides: object) -> GeneratedTestCase:
    payload = {
        "test_type": "positive",
        "operation_id": "listPets",
        "description": "List all pets",
        "request": {"method": "GET", "path": "/pets", "path_params": {}},
        "response": {"status_code": 200, "headers": {}, "schema_shape": None},
    }
    payload.update(overrides)
    return GeneratedTestCase.model_validate(payload)


def test_load_test_cases_filters_negative_types() -> None:
    """Test that non-'positive' test_type with a >=400 status is excluded."""
    positive = _test_case()
    negative = _test_case(
        test_type="negative_not_found",
        operation_id="showPetById",
        request={"method": "GET", "path": "/pets/{petId}", "path_params": {"petId": "999"}},
        response={"status_code": 404, "headers": {}, "schema_shape": None},
    )
    router = MockRouter()
    router.load_test_cases([positive, negative])
    assert router.match_route("GET", "/pets") is not None
    assert router.match_route("GET", "/pets/999") is None


def test_load_test_cases_negative_type_with_2xx_status_is_included() -> None:
    """Test that status < 400 counts as positive regardless of the test_type label."""
    case = _test_case(
        test_type="negative_auth_missing", response={"status_code": 200, "headers": {}}
    )
    router = MockRouter()
    router.load_test_cases([case])
    assert router.match_route("GET", "/pets") is not None


def test_path_parameter_substitution() -> None:
    """Test that path_params are substituted into path template placeholders."""
    case = _test_case(
        operation_id="showPetById",
        request={"method": "GET", "path": "/pets/{petId}", "path_params": {"petId": "42"}},
        response={"status_code": 200, "headers": {}, "schema_shape": None},
    )
    router = MockRouter()
    router.load_test_cases([case])
    route = router.match_route("GET", "/pets/42")
    assert route is not None
    assert route.path == "/pets/42"
    assert route.operation_id == "showPetById"


def test_trailing_slash_normalization_on_load_and_match() -> None:
    """Test that trailing slashes are stripped consistently for registration and lookup."""
    case = _test_case(request={"method": "GET", "path": "/pets/", "path_params": {}})
    router = MockRouter()
    router.load_test_cases([case])
    assert router.match_route("GET", "/pets") is not None
    assert router.match_route("GET", "/pets/") is not None


def test_root_path_not_stripped() -> None:
    """Test that the root path '/' is preserved rather than becoming empty."""
    case = _test_case(request={"method": "GET", "path": "/", "path_params": {}})
    router = MockRouter()
    router.load_test_cases([case])
    assert router.match_route("GET", "/") is not None


def test_method_matching_is_case_insensitive() -> None:
    """Test that incoming method casing is normalized before lookup."""
    case = _test_case()
    router = MockRouter()
    router.load_test_cases([case])
    assert router.match_route("get", "/pets") is not None


def test_response_body_synthesized_from_schema_shape() -> None:
    """Test that a matched route's body is synthesized deterministically from schema_shape."""
    case = _test_case(
        response={
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "schema_shape": {
                "type": "object",
                "required": ["id", "name"],
                "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
            },
        }
    )
    router = MockRouter()
    router.load_test_cases([case])
    route = router.match_route("GET", "/pets")
    assert route is not None
    assert json.loads(route.response.body) == {"id": 0, "name": "sample_name"}


def test_response_body_empty_for_204() -> None:
    """Test that a 204 status always yields an empty body regardless of schema_shape."""
    case = _test_case(
        operation_id="deletePet",
        request={"method": "DELETE", "path": "/pets/{petId}", "path_params": {"petId": "42"}},
        response={"status_code": 204, "headers": {}, "schema_shape": None},
    )
    router = MockRouter()
    router.load_test_cases([case])
    route = router.match_route("DELETE", "/pets/42")
    assert route is not None
    assert route.response.body == b""


def test_response_body_empty_when_schema_shape_none() -> None:
    """Test that a non-204 response with no schema_shape yields an empty body."""
    case = _test_case(response={"status_code": 200, "headers": {}, "schema_shape": None})
    router = MockRouter()
    router.load_test_cases([case])
    route = router.match_route("GET", "/pets")
    assert route is not None
    assert route.response.body == b""


def test_unmatched_route_returns_none() -> None:
    """Test that an unregistered (method, path) pair returns None."""
    router = MockRouter()
    router.load_test_cases([_test_case()])
    assert router.match_route("GET", "/unknown") is None


def test_duplicate_route_keeps_first_and_warns() -> None:
    """Test first-match precedence: a duplicate (method, path) fixture is ignored with a warning."""
    first = _test_case(
        operation_id="first",
        response={"status_code": 200, "headers": {}, "schema_shape": None},
    )
    second = _test_case(
        operation_id="second",
        response={"status_code": 200, "headers": {}, "schema_shape": None},
    )
    router = MockRouter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        router.load_test_cases([first, second])
    assert any("Duplicate" in str(w.message) for w in caught)
    route = router.match_route("GET", "/pets")
    assert route is not None
    assert route.operation_id == "first"


def test_find_allowed_methods_returns_sorted_methods_for_path() -> None:
    """Test find_allowed_methods returns all registered methods for a path, sorted."""
    get_case = _test_case()
    post_case = _test_case(
        operation_id="createPets", request={"method": "POST", "path": "/pets", "path_params": {}}
    )
    router = MockRouter()
    router.load_test_cases([get_case, post_case])
    assert router.find_allowed_methods("/pets") == ["GET", "POST"]


def test_find_allowed_methods_empty_for_unregistered_path() -> None:
    """Test find_allowed_methods returns an empty list for a path with no routes."""
    router = MockRouter()
    router.load_test_cases([_test_case()])
    assert router.find_allowed_methods("/unknown") == []


def test_build_not_found_response_structure() -> None:
    """Test the structured 404 diagnostic body shape per http-mock-contract.md."""
    router = MockRouter()
    router.load_test_cases([_test_case()])
    diagnostic = build_not_found_response("GET", "/unknown", router.routes)
    assert diagnostic["error"] == "Not Found"
    assert diagnostic["requested"] == {"method": "GET", "path": "/unknown"}
    assert diagnostic["available_routes"] == [
        {"method": "GET", "path": "/pets", "operation_id": "listPets"}
    ]


def test_build_method_not_allowed_response_structure() -> None:
    """Test the structured 405 diagnostic body shape per http-mock-contract.md."""
    diagnostic = build_method_not_allowed_response("DELETE", "/pets", ["GET", "POST"])
    assert diagnostic["error"] == "Method Not Allowed"
    assert diagnostic["requested"] == {"method": "DELETE", "path": "/pets"}
    assert diagnostic["allowed_methods"] == ["GET", "POST"]
