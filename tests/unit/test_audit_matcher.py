"""Unit tests for path template normalization and operation matching."""

from specprobe.audit.matcher import match_operation, match_path, normalize_path
from specprobe.audit.models import ArtifactTestItem


def test_normalize_path_templates() -> None:
    """Verify normalization of various path parameter styles."""
    # OpenAPI style
    assert normalize_path("/pets/{petId}") == "/pets/{}"
    # Postman colon style
    assert normalize_path("/pets/:petId") == "/pets/{}"
    # Postman / curly variable style
    assert normalize_path("/pets/{{petId}}") == "/pets/{}"
    assert normalize_path("{{baseUrl}}/pets/{{petId}}") == "/pets/{}"
    # Query string stripping
    assert normalize_path("/pets?limit=10&offset=0") == "/pets"
    # Trailing slash stripping
    assert normalize_path("/pets/") == "/pets"
    assert normalize_path("/") == "/"


def test_match_path_concrete_values() -> None:
    """Verify that concrete values in test paths match parameterized specification templates."""
    # Integer ID
    assert match_path("/pets/{petId}", "/pets/123") is True
    assert match_path("/pets/{petId}", "{{baseUrl}}/pets/42") is True
    # String slug
    assert match_path("/pets/{petId}", "/pets/fido-rover") is True
    # Multiple path parameters
    assert match_path("/users/{userId}/orders/{orderId}", "/users/10/orders/abc-99") is True
    # Mismatched segment count
    assert match_path("/pets/{petId}", "/pets") is False
    assert match_path("/pets", "/pets/123") is False
    # Completely different path
    assert match_path("/pets/{petId}", "/owners/123") is False


def test_match_operation_method_and_path() -> None:
    """Verify operation matching considers HTTP method and path."""
    item = ArtifactTestItem(
        name="Get Pet",
        method="get",
        path="{{baseUrl}}/pets/42",
    )

    # Correct method and path
    assert match_operation("GET", "/pets/{petId}", item) is True
    assert match_operation("get", "/pets/{petId}", item) is True

    # Method mismatch
    assert match_operation("DELETE", "/pets/{petId}", item) is False
    assert match_operation("POST", "/pets/{petId}", item) is False

    # Path mismatch
    assert match_operation("GET", "/pets", item) is False
