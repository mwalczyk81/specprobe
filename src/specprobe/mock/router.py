"""Route table construction and request matching for the mock HTTP server."""

import json
import warnings
from collections.abc import Iterable
from typing import Any

from specprobe.generator.models import GeneratedTestCase, ResponseAssertion
from specprobe.mock.models import MockResponse, MockRoute
from specprobe.mock.synth import synthesize_sample_from_schema

__all__ = [
    "MockRouter",
    "build_not_found_response",
    "build_method_not_allowed_response",
]


class MockRouter:
    """In-memory route registry keyed on (normalized_method, normalized_path)."""

    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], MockRoute] = {}

    @property
    def routes(self) -> list[MockRoute]:
        """Registered routes in registration order."""
        return list(self._routes.values())

    def load_test_cases(self, test_cases: Iterable[GeneratedTestCase]) -> None:
        """Register positive test cases as routes, resolving path parameters and
        normalizing trailing slashes. Later fixtures targeting an already-registered
        (method, path) pair are ignored with a warning (first-match precedence).
        """
        for test_case in test_cases:
            if not _is_positive(test_case):
                continue
            route = _build_route(test_case)
            if route is None:
                continue
            key = (route.method, route.path)
            if key in self._routes:
                warnings.warn(
                    f"Duplicate mock route {key[0]} {key[1]} for operation "
                    f"'{route.operation_id}': keeping first registered fixture.",
                    stacklevel=2,
                )
                continue
            self._routes[key] = route

    def match_route(self, method: str, path: str) -> MockRoute | None:
        """Look up a registered route by normalized method and path."""
        return self._routes.get((method.upper(), _normalize_path(path)))

    def find_allowed_methods(self, path: str) -> list[str]:
        """Return the sorted list of HTTP methods registered for a normalized path."""
        normalized_path = _normalize_path(path)
        return sorted({method for method, p in self._routes if p == normalized_path})


def build_not_found_response(method: str, path: str, routes: list[MockRoute]) -> dict[str, Any]:
    """Build the structured 404 diagnostic body listing all available routes."""
    return {
        "error": "Not Found",
        "message": f"No mock route registered for path '{path}'",
        "requested": {"method": method.upper(), "path": path},
        "available_routes": [
            {"method": route.method, "path": route.path, "operation_id": route.operation_id}
            for route in routes
        ],
    }


def build_method_not_allowed_response(
    method: str, path: str, allowed_methods: list[str]
) -> dict[str, Any]:
    """Build the structured 405 diagnostic body listing allowed methods for the path."""
    return {
        "error": "Method Not Allowed",
        "message": f"Method '{method.upper()}' is not supported for path '{path}'",
        "requested": {"method": method.upper(), "path": path},
        "allowed_methods": allowed_methods,
    }


def _is_positive(test_case: GeneratedTestCase) -> bool:
    return test_case.test_type == "positive" or test_case.response.status_code < 400


def _build_route(test_case: GeneratedTestCase) -> MockRoute | None:
    request = test_case.request
    if not request.method or not request.path:
        return None
    method = request.method.upper()
    path = _normalize_path(_resolve_path(request.path, request.path_params))
    response = _build_response(test_case.response)
    return MockRoute(
        method=method,
        path=path,
        operation_id=test_case.operation_id,
        response=response,
        tags=list(test_case.tags),
    )


def _build_response(assertion: ResponseAssertion) -> MockResponse:
    if assertion.status_code == 204 or assertion.schema_shape is None:
        body = b""
    else:
        sample = synthesize_sample_from_schema(assertion.schema_shape)
        body = json.dumps(sample).encode("utf-8")
    return MockResponse(
        status_code=assertion.status_code,
        headers=dict(assertion.headers),
        body=body,
    )


def _resolve_path(template: str, path_params: dict[str, Any]) -> str:
    resolved = template
    for name, value in path_params.items():
        resolved = resolved.replace("{" + name + "}", str(value))
    return resolved


def _normalize_path(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return path
