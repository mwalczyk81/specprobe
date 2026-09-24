"""Route table construction and request matching for the mock HTTP server."""

import json
import re
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

_PLACEHOLDER_PATTERN = re.compile(r"\{[^/{}]+\}")


class MockRouter:
    """In-memory route registry.

    Every route is registered at its concrete path (the fixture's `path_params`
    substituted into its template). Positive routes additionally match any value in
    their template's placeholder segments, so `/pets/{petId}` serves `/pets/7` as
    well as the fixture's own `/pets/42`. Lookup tries the exact path first, then
    templates from most to least literal segments, so `/pets/search` beats
    `/pets/{petId}` and a 404 fixture's sentinel path beats the positive template.
    """

    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], MockRoute] = {}
        self._templates: list[tuple[re.Pattern[str], int, MockRoute]] = []

    @property
    def routes(self) -> list[MockRoute]:
        """Registered routes in registration order."""
        return list(self._routes.values())

    def load_test_cases(self, test_cases: Iterable[GeneratedTestCase]) -> None:
        """Register positive and 404 test cases as routes, resolving path parameters
        and normalizing trailing slashes. Later fixtures targeting an already-registered
        (method, path) pair are ignored with a warning (first-match precedence).

        404 fixtures are registered at their concrete sentinel path only: they differ
        from the positive route by path alone, so the mock can serve them faithfully.
        Other negatives (401/403/400) differ only by headers or body, which matching
        ignores, so they are skipped.
        """
        for test_case in test_cases:
            if _is_positive(test_case):
                route = _build_route(test_case, templated=True)
            elif test_case.test_type == "negative_not_found":
                route = _build_route(test_case, templated=False)
            else:
                continue
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
            if route.path_template is not None:
                self._templates.append(
                    (
                        _compile_template(route.path_template),
                        _literal_segment_count(route.path_template),
                        route,
                    )
                )
        # Stable sort: equally specific templates keep registration order.
        self._templates.sort(key=lambda entry: -entry[1])

    def match_route(self, method: str, path: str) -> MockRoute | None:
        """Look up a route by exact normalized path, falling back to path templates."""
        normalized_method = method.upper()
        normalized_path = _normalize_path(path)
        exact = self._routes.get((normalized_method, normalized_path))
        if exact is not None:
            return exact
        for pattern, _literals, route in self._templates:
            if route.method == normalized_method and pattern.fullmatch(normalized_path):
                return route
        return None

    def find_allowed_methods(self, path: str) -> list[str]:
        """Return the sorted HTTP methods whose exact path or template matches `path`."""
        normalized_path = _normalize_path(path)
        methods = {method for method, p in self._routes if p == normalized_path}
        methods.update(
            route.method
            for pattern, _literals, route in self._templates
            if pattern.fullmatch(normalized_path)
        )
        return sorted(methods)


def build_not_found_response(method: str, path: str, routes: list[MockRoute]) -> dict[str, Any]:
    """Build the structured 404 diagnostic body listing all available routes."""
    return {
        "error": "Not Found",
        "message": f"No mock route registered for path '{path}'",
        "requested": {"method": method.upper(), "path": path},
        "available_routes": [
            {
                "method": route.method,
                "path": route.path,
                "path_template": route.path_template,
                "operation_id": route.operation_id,
            }
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


def _build_route(test_case: GeneratedTestCase, templated: bool) -> MockRoute | None:
    request = test_case.request
    if not request.method or not request.path:
        return None
    method = request.method.upper()
    path = _normalize_path(_resolve_path(request.path, request.path_params))
    template = _normalize_path(request.path)
    has_placeholder = _PLACEHOLDER_PATTERN.search(template) is not None
    response = _build_response(test_case.response)
    return MockRoute(
        method=method,
        path=path,
        path_template=template if templated and has_placeholder else None,
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


def _compile_template(template: str) -> re.Pattern[str]:
    """Compile a path template so each `{placeholder}` matches one non-empty run of
    non-slash characters (a whole segment, or a fragment as in `/files/{name}.{ext}`)."""
    literal_parts = _PLACEHOLDER_PATTERN.split(template)
    return re.compile("[^/]+".join(re.escape(part) for part in literal_parts))


def _literal_segment_count(template: str) -> int:
    return sum(1 for segment in template.split("/") if not _PLACEHOLDER_PATTERN.search(segment))


def _normalize_path(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return path
