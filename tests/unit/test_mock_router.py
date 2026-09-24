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


def test_load_test_cases_skips_header_and_body_negatives() -> None:
    """Test that 401/403/400 negatives are excluded: they differ from the positive
    request only by headers or body, which matching ignores."""
    positive = _test_case()
    negatives = [
        _test_case(
            test_type=test_type,
            response={"status_code": status, "headers": {}, "schema_shape": None},
        )
        for test_type, status in [
            ("negative_auth_missing", 401),
            ("negative_auth_invalid", 403),
            ("negative_invalid_input", 400),
        ]
    ]
    router = MockRouter()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        router.load_test_cases([positive, *negatives])
    assert len(router.routes) == 1
    route = router.match_route("GET", "/pets")
    assert route is not None
    assert route.response.status_code == 200


def test_not_found_fixture_served_at_sentinel_path_only() -> None:
    """Test that a 404 fixture is registered at its concrete sentinel path and wins
    over the positive template there, without shadowing any other value."""
    positive = _test_case(
        operation_id="showPetById",
        request={"method": "GET", "path": "/pets/{petId}", "path_params": {"petId": "42"}},
    )
    not_found = _test_case(
        test_type="negative_not_found",
        operation_id="showPetById",
        request={"method": "GET", "path": "/pets/{petId}", "path_params": {"petId": "999"}},
        response={"status_code": 404, "headers": {}, "schema_shape": None},
    )
    router = MockRouter()
    router.load_test_cases([not_found, positive])

    sentinel_route = router.match_route("GET", "/pets/999")
    assert sentinel_route is not None
    assert sentinel_route.response.status_code == 404
    assert sentinel_route.path_template is None

    other_route = router.match_route("GET", "/pets/7")
    assert other_route is not None
    assert other_route.response.status_code == 200


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
        {"method": "GET", "path": "/pets", "path_template": None, "operation_id": "listPets"}
    ]


def test_build_method_not_allowed_response_structure() -> None:
    """Test the structured 405 diagnostic body shape per http-mock-contract.md."""
    diagnostic = build_method_not_allowed_response("DELETE", "/pets", ["GET", "POST"])
    assert diagnostic["error"] == "Method Not Allowed"
    assert diagnostic["requested"] == {"method": "DELETE", "path": "/pets"}
    assert diagnostic["allowed_methods"] == ["GET", "POST"]


def _show_pet(pet_id: str = "42", **overrides: object) -> GeneratedTestCase:
    fields: dict[str, object] = {
        "operation_id": "showPetById",
        "request": {"method": "GET", "path": "/pets/{petId}", "path_params": {"petId": pet_id}},
    }
    fields.update(overrides)
    return _test_case(**fields)


def test_template_matches_any_value_in_placeholder_segment() -> None:
    """Test that a positive route serves every concrete value of its path parameter."""
    router = MockRouter()
    router.load_test_cases([_show_pet()])
    for path in ("/pets/42", "/pets/7", "/pets/abc-123", "/pets/7/"):
        route = router.match_route("GET", path)
        assert route is not None, path
        assert route.operation_id == "showPetById"
    route = router.match_route("GET", "/pets/7")
    assert route is not None
    assert route.path == "/pets/42"
    assert route.path_template == "/pets/{petId}"


def test_template_does_not_span_segments_or_match_empty() -> None:
    """Test that a placeholder matches exactly one non-empty segment."""
    router = MockRouter()
    router.load_test_cases([_show_pet()])
    assert router.match_route("GET", "/pets") is None
    assert router.match_route("GET", "/pets/7/toys") is None
    assert router.match_route("GET", "/other/7") is None


def test_template_respects_method() -> None:
    """Test that a template only matches its own HTTP method."""
    router = MockRouter()
    router.load_test_cases([_show_pet()])
    assert router.match_route("DELETE", "/pets/7") is None


def test_template_with_multiple_and_fragment_placeholders() -> None:
    """Test multi-parameter templates and placeholders sharing a segment with literals."""
    nested = _test_case(
        operation_id="getDocument",
        request={
            "method": "GET",
            "path": "/accounts/{accountId}/documents/{documentId}",
            "path_params": {"accountId": "a1", "documentId": "d1"},
        },
    )
    fragment = _test_case(
        operation_id="getFile",
        request={
            "method": "GET",
            "path": "/files/{name}.{ext}",
            "path_params": {"name": "report", "ext": "pdf"},
        },
    )
    router = MockRouter()
    router.load_test_cases([nested, fragment])

    route = router.match_route("GET", "/accounts/zz/documents/yy")
    assert route is not None
    assert route.operation_id == "getDocument"

    route = router.match_route("GET", "/files/summary.csv")
    assert route is not None
    assert route.operation_id == "getFile"
    assert router.match_route("GET", "/files/summary") is None


def test_template_literals_are_not_regex() -> None:
    """Test that regex metacharacters in literal segments match only themselves."""
    case = _test_case(
        operation_id="versioned",
        request={"method": "GET", "path": "/v1.0/items/{id}", "path_params": {"id": "1"}},
    )
    router = MockRouter()
    router.load_test_cases([case])
    assert router.match_route("GET", "/v1.0/items/9") is not None
    assert router.match_route("GET", "/v1x0/items/9") is None


def test_literal_route_beats_template_regardless_of_order() -> None:
    """Test that `/pets/search` wins over `/pets/{petId}` even if registered later."""
    search = _test_case(
        operation_id="searchPets",
        request={"method": "GET", "path": "/pets/search", "path_params": {}},
    )
    router = MockRouter()
    router.load_test_cases([_show_pet(), search])
    route = router.match_route("GET", "/pets/search")
    assert route is not None
    assert route.operation_id == "searchPets"


def test_more_literal_template_wins() -> None:
    """Test specificity ordering between two templates that both match a path."""
    generic = _test_case(
        operation_id="getSubresource",
        request={
            "method": "GET",
            "path": "/accounts/{id}/{sub}",
            "path_params": {"id": "1", "sub": "x"},
        },
    )
    specific = _test_case(
        operation_id="getBalances",
        request={
            "method": "GET",
            "path": "/accounts/{id}/balances",
            "path_params": {"id": "1"},
        },
    )
    router = MockRouter()
    router.load_test_cases([generic, specific])

    route = router.match_route("GET", "/accounts/9/balances")
    assert route is not None
    assert route.operation_id == "getBalances"

    route = router.match_route("GET", "/accounts/9/details")
    assert route is not None
    assert route.operation_id == "getSubresource"


def test_equally_specific_templates_keep_registration_order() -> None:
    """Test that the first-registered template wins among equally specific ones."""
    first = _show_pet(operation_id="first")
    second = _test_case(
        operation_id="second",
        request={"method": "GET", "path": "/pets/{name}", "path_params": {"name": "rex"}},
    )
    router = MockRouter()
    router.load_test_cases([first, second])
    route = router.match_route("GET", "/pets/anything")
    assert route is not None
    assert route.operation_id == "first"


def test_exact_fixture_path_beats_other_template() -> None:
    """Test that a route's own concrete path is served by that route, not by an
    earlier template that also happens to match it."""
    first = _show_pet(operation_id="first")
    second = _test_case(
        operation_id="second",
        request={"method": "GET", "path": "/pets/{name}", "path_params": {"name": "rex"}},
    )
    router = MockRouter()
    router.load_test_cases([first, second])
    route = router.match_route("GET", "/pets/rex")
    assert route is not None
    assert route.operation_id == "second"


def test_unresolved_placeholder_still_templates() -> None:
    """Test that a template whose path_params omit a placeholder still matches values."""
    case = _test_case(
        operation_id="showPetById",
        request={"method": "GET", "path": "/pets/{petId}", "path_params": {}},
    )
    router = MockRouter()
    router.load_test_cases([case])
    route = router.match_route("GET", "/pets/5")
    assert route is not None
    assert route.path == "/pets/{petId}"


def test_fixture_path_without_leading_slash_is_normalized() -> None:
    """Test that a relative fixture path registers (and templates) as absolute."""
    case = _test_case(
        operation_id="showPetById",
        request={"method": "GET", "path": "pets/{petId}", "path_params": {"petId": "1"}},
    )
    router = MockRouter()
    router.load_test_cases([case])
    route = router.match_route("GET", "/pets/9")
    assert route is not None
    assert route.path == "/pets/1"
    assert route.path_template == "/pets/{petId}"


def test_literal_only_route_has_no_template() -> None:
    """Test that a path without placeholders is exact-match only."""
    router = MockRouter()
    router.load_test_cases([_test_case()])
    assert router.routes[0].path_template is None


def test_fixture_without_method_or_path_is_skipped() -> None:
    """Test that a fixture missing its method or path registers no route."""
    router = MockRouter()
    router.load_test_cases(
        [
            _test_case(request={"method": None, "path": "/pets", "path_params": {}}),
            _test_case(request={"method": "GET", "path": None, "path_params": {}}),
        ]
    )
    assert router.routes == []


def test_find_allowed_methods_includes_template_matches() -> None:
    """Test that 405 detection sees methods registered via templates."""
    delete = _test_case(
        operation_id="deletePet",
        request={"method": "DELETE", "path": "/pets/{petId}", "path_params": {"petId": "1"}},
    )
    router = MockRouter()
    router.load_test_cases([_show_pet(), delete])
    assert router.find_allowed_methods("/pets/77") == ["DELETE", "GET"]
    assert router.find_allowed_methods("/pets/77/toys") == []


def test_not_found_diagnostic_lists_templates() -> None:
    """Test that the 404 body exposes each route's template alongside its fixture path."""
    router = MockRouter()
    router.load_test_cases([_show_pet()])
    diagnostic = build_not_found_response("GET", "/nope", router.routes)
    assert diagnostic["available_routes"] == [
        {
            "method": "GET",
            "path": "/pets/42",
            "path_template": "/pets/{petId}",
            "operation_id": "showPetById",
        }
    ]
