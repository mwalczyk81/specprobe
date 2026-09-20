"""Deterministic negative authentication test case generation (401/403).

Strictly adheres to SpecProbe Constitution Principle II: zero-LLM, fully deterministic
generation of negative authentication test cases derived algorithmically from
validated happy-path test cases and OpenAPI security scheme components.
"""

import copy
import re
from typing import Any

from specprobe.chunker.models import OperationChunk
from specprobe.exporter.security import ResolvedCredential, SecurityResolver
from specprobe.generator.models import GeneratedTestCase, ResponseAssertion

__all__ = [
    "is_secured_operation",
    "get_all_security_target_names",
    "get_invalid_credential_literal",
    "generate_401_test_case",
    "generate_403_test_case",
    "generate_negative_auth_test_cases",
]


def is_secured_operation(security: list[dict[str, list[str]]] | None) -> bool:
    """Determine whether an operation requires authentication.

    Returns True if security requirements exist and at least one requirement
    is non-empty (requiring at least one active scheme). Returns False for
    unsecured endpoints (security is None or empty) and endpoints with only
    optional security (represented by [{}]).
    """
    if not security:
        return False
    # An operation is secured if there is at least one non-empty requirement
    # and not purely optional (if {} is one alternative, optional security
    # is not enforced for 401/403)
    has_optional = any(len(req) == 0 for req in security)
    if has_optional:
        return False
    return any(len(req) > 0 for req in security)


def get_all_security_target_names(
    security_requirements: list[dict[str, list[str]]],
    security_schemes: dict[str, Any],
) -> tuple[set[str], set[str]]:
    """Collect all header names and query parameter names used across all declared schemes.

    Returns
    -------
    tuple[set[str], set[str]]
        (header_names, query_param_names) in lowercase for case-insensitive matching.
    """
    headers: set[str] = set()
    query_params: set[str] = set()

    for req in security_requirements:
        for scheme_name in req.keys():
            _, transport, target_name, _, _ = SecurityResolver._get_scheme_priority_and_details(
                scheme_name, security_schemes
            )
            if transport == "header":
                headers.add(target_name.lower())
            elif transport == "query":
                query_params.add(target_name.lower())

    # Always include Authorization header if any scheme could use it
    has_auth_scheme = any(
        "bearer" in s.lower() or "basic" in s.lower() or "oauth" in s.lower()
        for req in security_requirements
        for s in req.keys()
    )
    if has_auth_scheme:
        headers.add("authorization")

    return headers, query_params


def get_invalid_credential_literal(
    cred: ResolvedCredential,
    security_schemes: dict[str, Any] | None = None,
) -> str:
    """Generate a protocol-valid invalid literal value for the given credential.

    Ensures HTTP parsers and gateway middleware validate the token syntax and
    pass the request to authentication logic rather than rejecting it with 400 Bad Request.
    """
    schemes = security_schemes or {}
    def_obj = schemes.get(cred.scheme_name, {})

    if cred.transport == "header" and cred.target_name.lower() == "authorization":
        if "basic" in cred.wire_value_template.lower() or (
            isinstance(def_obj, dict) and str(def_obj.get("scheme", "")).lower() == "basic"
        ):
            return "Basic aW52YWxpZDppbnZhbGlk"  # base64 of "invalid:invalid"
        # Bearer / OAuth2 default
        return "Bearer invalid_token"

    clean_target = re.sub(r"[^a-zA-Z0-9_]+", "_", cred.target_name).lower().strip("_")
    if not clean_target:
        clean_target = "auth"
    if clean_target.endswith("key"):
        return f"invalid_{clean_target}"
    return f"invalid_{clean_target}_key"


def generate_401_test_case(
    happy_tc: GeneratedTestCase,
    chunk: OperationChunk | None = None,
) -> GeneratedTestCase:
    """Synthesize a 401 Unauthorized negative test case by omitting all credentials.

    Clones the happy-path request, strips all authentication headers and query
    parameters associated with any declared scheme, and asserts HTTP 401.
    """
    sec_reqs = happy_tc.security or (chunk.metadata.security if chunk else [])
    sec_schemes = happy_tc.security_schemes or (
        chunk.components.get("securitySchemes", {})
        if chunk and isinstance(chunk.components, dict)
        else {}
    )

    sec_headers, sec_queries = get_all_security_target_names(sec_reqs, sec_schemes)

    req_clone = copy.deepcopy(happy_tc.request)

    # Strip authentication headers
    filtered_headers = {k: v for k, v in req_clone.headers.items() if k.lower() not in sec_headers}
    req_clone.headers = filtered_headers

    # Strip authentication query parameters
    filtered_query = {
        k: v for k, v in req_clone.query_params.items() if k.lower() not in sec_queries
    }
    req_clone.query_params = filtered_query

    # Response assertion: 401 status code, null schema shape (unless documented in chunk)
    resp_schema = None
    if chunk and isinstance(chunk.operation, dict):
        responses = chunk.operation.get("responses", {})
        if isinstance(responses, dict):
            resp_401 = responses.get("401")
            if isinstance(resp_401, dict):
                content = resp_401.get("content", {})
                if isinstance(content, dict):
                    app_json = content.get("application/json", {})
                    if isinstance(app_json, dict) and "schema" in app_json:
                        resp_schema = app_json["schema"]

    response = ResponseAssertion(
        status_code=401,
        headers={"Content-Type": "application/json"} if resp_schema else {},
        schema_shape=resp_schema,
    )

    # Tags: preserve primary tag first, append ["negative", "auth", "401"]
    new_tags = list(happy_tc.tags)
    for t in ["negative", "auth", "401"]:
        if t not in new_tags:
            new_tags.append(t)

    return GeneratedTestCase(
        test_type="negative_auth_missing",
        operation_id=happy_tc.operation_id,
        description=f"[401] Missing authentication credentials - {happy_tc.operation_id}",
        request=req_clone,
        response=response,
        tags=new_tags,
        security=copy.deepcopy(sec_reqs),
        security_schemes=copy.deepcopy(sec_schemes),
    )


def generate_403_test_case(
    happy_tc: GeneratedTestCase,
    chunk: OperationChunk | None = None,
) -> GeneratedTestCase:
    """Synthesize a 403 Forbidden negative test case by corrupting primary credentials.

    Clones the happy-path request, identifies the primary winning security scheme,
    replaces its value with a protocol-valid invalid literal, and asserts HTTP 403.
    """
    sec_reqs = happy_tc.security or (chunk.metadata.security if chunk else [])
    sec_schemes = happy_tc.security_schemes or (
        chunk.components.get("securitySchemes", {})
        if chunk and isinstance(chunk.components, dict)
        else {}
    )

    resolved_creds = SecurityResolver.resolve_credentials(sec_reqs, sec_schemes)
    if not resolved_creds:
        # Fallback if somehow called on unresolvable
        return generate_401_test_case(happy_tc, chunk)

    primary_cred = resolved_creds[0]
    invalid_literal = get_invalid_credential_literal(primary_cred, sec_schemes)

    req_clone = copy.deepcopy(happy_tc.request)

    if primary_cred.transport == "header":
        # Find existing header case-insensitively or set target_name
        existing_key = next(
            (k for k in req_clone.headers.keys() if k.lower() == primary_cred.target_name.lower()),
            None,
        )
        if existing_key:
            req_clone.headers[existing_key] = invalid_literal
        else:
            req_clone.headers[primary_cred.target_name] = invalid_literal
    elif primary_cred.transport == "query":
        req_clone.query_params[primary_cred.target_name] = invalid_literal

    # Response assertion: 403 status code, null schema shape (unless documented in chunk)
    resp_schema = None
    if chunk and isinstance(chunk.operation, dict):
        responses = chunk.operation.get("responses", {})
        if isinstance(responses, dict):
            resp_403 = responses.get("403")
            if isinstance(resp_403, dict):
                content = resp_403.get("content", {})
                if isinstance(content, dict):
                    app_json = content.get("application/json", {})
                    if isinstance(app_json, dict) and "schema" in app_json:
                        resp_schema = app_json["schema"]

    response = ResponseAssertion(
        status_code=403,
        headers={"Content-Type": "application/json"} if resp_schema else {},
        schema_shape=resp_schema,
    )

    # Tags: preserve primary tag first, append ["negative", "auth", "403"]
    new_tags = list(happy_tc.tags)
    for t in ["negative", "auth", "403"]:
        if t not in new_tags:
            new_tags.append(t)

    return GeneratedTestCase(
        test_type="negative_auth_invalid",
        operation_id=happy_tc.operation_id,
        description=f"[403] Invalid authentication credentials - {happy_tc.operation_id}",
        request=req_clone,
        response=response,
        tags=new_tags,
        security=copy.deepcopy(sec_reqs),
        security_schemes=copy.deepcopy(sec_schemes),
    )


def generate_negative_auth_test_cases(
    happy_tc: GeneratedTestCase,
    chunk: OperationChunk | None = None,
) -> list[GeneratedTestCase]:
    """Generate both 401 and 403 negative authentication test cases for a secured operation.

    Returns an empty list if the operation is unsecured or optional.
    """
    sec_reqs = happy_tc.security or (chunk.metadata.security if chunk else [])
    if not is_secured_operation(sec_reqs):
        return []

    tc_401 = generate_401_test_case(happy_tc, chunk)
    tc_403 = generate_403_test_case(happy_tc, chunk)
    return [tc_401, tc_403]
