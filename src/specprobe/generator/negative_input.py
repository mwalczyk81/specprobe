"""Deterministic negative input and resource test case generation (404/400).

Strictly adheres to SpecProbe Constitution Principle II: zero-LLM, fully deterministic
generation of negative test cases derived algorithmically from validated happy-path
test cases, path parameters, and request body schemas.
"""

import copy
import re
from typing import Any

from pydantic import ValidationError

from specprobe.chunker.models import OperationChunk
from specprobe.generator.models import GeneratedTestCase, ResponseAssertion

__all__ = [
    "PathParameterMutator",
    "RequestBodyMutator",
    "generate_404_test_case",
    "generate_400_test_case",
    "generate_negative_input_test_cases",
]


class PathParameterMutator:
    """Deterministic path parameter mutator for 404 Not Found generation."""

    SENTINEL_INTEGER: int = 999999
    SENTINEL_NIL_UUID: str = "00000000-0000-0000-0000-000000000000"
    SENTINEL_STRING_SLUG: str = "specprobe-nonexistent-id"

    @classmethod
    def find_leaf_path_parameter(
        cls,
        path_template: str,
        parameters: list[dict[str, Any]] | None = None,
    ) -> tuple[str, dict[str, Any]] | None:
        """Locate the last path parameter in the route template and its definition.

        Parameters
        ----------
        path_template : str
            Route path template (e.g. "/orgs/{orgId}/teams/{teamId}").
        parameters : list[dict[str, Any]] | None
            Operation and path-level parameter definitions from OpenAPI chunk.

        Returns
        -------
        tuple[str, dict[str, Any]] | None
            (parameter_name, parameter_definition) for the leaf parameter,
            or None if no path parameters exist in the template.
        """
        param_names = re.findall(r"\{([^}]+)\}", path_template)
        if not param_names:
            return None

        leaf_name = param_names[-1]
        param_defs = parameters or []

        leaf_def: dict[str, Any] = {"name": leaf_name, "in": "path"}
        for p in param_defs:
            if isinstance(p, dict) and p.get("in") == "path" and p.get("name") == leaf_name:
                leaf_def = p
                break

        return leaf_name, leaf_def

    @classmethod
    def get_nonexistent_sentinel(cls, param_def: dict[str, Any]) -> Any:
        """Determine the nonexistent value based on parameter schema type and format.

        Parameters
        ----------
        param_def : dict[str, Any]
            OpenAPI parameter object or schema definition.

        Returns
        -------
        Any
            Deterministic sentinel value:
            - integer / number: 999999
            - format uuid: "00000000-0000-0000-0000-000000000000"
            - string / enum / general: "specprobe-nonexistent-id"
        """
        schema = (
            param_def.get("schema", {}) if isinstance(param_def.get("schema"), dict) else param_def
        )

        p_type = schema.get("type") or param_def.get("type")
        p_format = schema.get("format") or param_def.get("format")

        if p_type in ("integer", "number"):
            return cls.SENTINEL_INTEGER

        if p_format == "uuid":
            return cls.SENTINEL_NIL_UUID

        return cls.SENTINEL_STRING_SLUG

    @classmethod
    def mutate_path_params(
        cls,
        path_template: str,
        current_params: dict[str, Any],
        parameters: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Return a copy of path_params with only the leaf parameter mutated.

        Parameters
        ----------
        path_template : str
            Route path template (e.g. "/pets/{petId}").
        current_params : dict[str, Any]
            Current path parameter map from the positive test case.
        parameters : list[dict[str, Any]] | None
            OpenAPI parameter definitions.

        Returns
        -------
        dict[str, Any] | None
            Mutated path_params dictionary, or None if the route has no path parameters.
        """
        leaf = cls.find_leaf_path_parameter(path_template, parameters)
        if leaf is None:
            return None

        leaf_name, leaf_def = leaf
        sentinel = cls.get_nonexistent_sentinel(leaf_def)

        mutated = copy.deepcopy(current_params)
        mutated[leaf_name] = sentinel
        return mutated


class RequestBodyMutator:
    """Deterministic request body mutator for 400 Bad Request generation."""

    TYPE_CORRUPTIONS: dict[str, Any] = {
        "string": ["__specprobe_invalid_type__"],
        "integer": "__specprobe_not_a_number__",
        "number": "__specprobe_not_a_number__",
        "boolean": "__specprobe_not_a_boolean__",
        "array": "__specprobe_not_an_array__",
        "object": "__specprobe_not_an_object__",
    }

    @classmethod
    def get_json_schema(cls, chunk: OperationChunk) -> dict[str, Any] | None:
        """Extract the JSON request body schema if present and constrained.

        Parameters
        ----------
        chunk : OperationChunk
            OpenAPI operation chunk.

        Returns
        -------
        dict[str, Any] | None
            Resolved JSON Schema object, or None if bodiless, non-JSON, or unconstrained.
        """
        if not isinstance(chunk.operation, dict):
            return None

        request_body = chunk.operation.get("requestBody")
        if not isinstance(request_body, dict):
            return None

        content = request_body.get("content")
        if not isinstance(content, dict):
            return None

        media_obj: dict[str, Any] | None = None
        for media_type, obj in content.items():
            base_type = media_type.lower().split(";")[0].strip()
            if base_type == "application/json" or (
                base_type.startswith("application/") and base_type.endswith("+json")
            ):
                if isinstance(obj, dict):
                    media_obj = obj
                    break

        if not media_obj or not isinstance(media_obj, dict):
            return None

        schema = media_obj.get("schema")
        if not isinstance(schema, dict):
            return None

        # Resolve local components.schemas reference if present
        current = schema
        schemas = chunk.components.get("schemas", {}) if isinstance(chunk.components, dict) else {}
        visited: set[str] = set()
        while isinstance(current, dict) and "$ref" in current:
            ref = current["$ref"]
            if ref in visited:
                break
            visited.add(ref)
            if ref.startswith("#/components/schemas/"):
                name = ref.split("/")[-1]
                if name in schemas and isinstance(schemas[name], dict):
                    current = schemas[name]
                    continue
            break

        # Check for meaningful constraints
        meaningful_keys = {
            "type",
            "properties",
            "required",
            "items",
            "allOf",
            "anyOf",
            "oneOf",
            "enum",
        }
        if not any(k in current for k in meaningful_keys):
            return None

        return current

    @classmethod
    def mutate_json_body(cls, body: Any, schema: dict[str, Any]) -> Any | None:
        """Apply minimal violation: omit first required property or invert first property type.

        Priority hierarchy:
        1. Omit first declared required property present in body.
        2. Invert first declared property type in schema.get("properties").
        3. Root array inversion: replace list body with empty object {}.

        Parameters
        ----------
        body : Any
            Valid positive request body payload.
        schema : dict[str, Any]
            Resolved request body schema.

        Returns
        -------
        Any | None
            Mutated invalid payload, or None if body cannot be violated.
        """
        if body is None:
            return None

        # Root array inversion
        if isinstance(body, list):
            return {}

        if isinstance(body, dict):
            # 1. Omit first required property present in body
            required = schema.get("required")
            if isinstance(required, list):
                for req_prop in required:
                    if req_prop in body:
                        mutated = copy.deepcopy(body)
                        del mutated[req_prop]
                        return mutated

            # 2. Invert first declared property type
            properties = schema.get("properties")
            if isinstance(properties, dict) and properties:
                for prop_name, prop_schema in properties.items():
                    if prop_name in body:
                        prop_type = (
                            prop_schema.get("type") if isinstance(prop_schema, dict) else None
                        )
                        if not prop_type or prop_type not in cls.TYPE_CORRUPTIONS:
                            val = body[prop_name]
                            if isinstance(val, bool):
                                prop_type = "boolean"
                            elif isinstance(val, int):
                                prop_type = "integer"
                            elif isinstance(val, float):
                                prop_type = "number"
                            elif isinstance(val, str):
                                prop_type = "string"
                            elif isinstance(val, list):
                                prop_type = "array"
                            elif isinstance(val, dict):
                                prop_type = "object"
                            else:
                                prop_type = "string"

                        corruption = cls.TYPE_CORRUPTIONS.get(
                            prop_type, ["__specprobe_invalid_type__"]
                        )
                        mutated = copy.deepcopy(body)
                        mutated[prop_name] = copy.deepcopy(corruption)
                        return mutated

            # Fallback if body has keys not enumerated in properties
            if body:
                first_key = next(iter(body.keys()))
                val = body[first_key]
                if isinstance(val, bool):
                    prop_type = "boolean"
                elif isinstance(val, int):
                    prop_type = "integer"
                elif isinstance(val, float):
                    prop_type = "number"
                elif isinstance(val, str):
                    prop_type = "string"
                elif isinstance(val, list):
                    prop_type = "array"
                elif isinstance(val, dict):
                    prop_type = "object"
                else:
                    prop_type = "string"

                corruption = cls.TYPE_CORRUPTIONS.get(prop_type, ["__specprobe_invalid_type__"])
                mutated = copy.deepcopy(body)
                mutated[first_key] = copy.deepcopy(corruption)
                return mutated

            # If body is empty dict {} but schema expects object
            return "__specprobe_not_an_object__"

        if isinstance(body, str):
            return ["__specprobe_invalid_type__"]

        if isinstance(body, (int, float)):
            return "__specprobe_not_a_number__"

        if isinstance(body, bool):
            return "__specprobe_not_a_boolean__"

        return None


def generate_404_test_case(
    positive_tc: GeneratedTestCase,
    chunk: OperationChunk,
) -> GeneratedTestCase | None:
    """Generate a 404 Not Found negative test case by mutating the leaf path parameter.

    Parameters
    ----------
    positive_tc : GeneratedTestCase
        The valid happy-path test case.
    chunk : OperationChunk
        OpenAPI operation chunk containing path template and parameter schemas.

    Returns
    -------
    GeneratedTestCase | None
        404 test case instance, or None if the operation has no path parameters.
    """
    path_template = chunk.metadata.path or positive_tc.request.path or ""
    parameters = chunk.operation.get("parameters", []) if isinstance(chunk.operation, dict) else []

    mutated_params = PathParameterMutator.mutate_path_params(
        path_template,
        positive_tc.request.path_params,
        parameters,
    )
    if mutated_params is None:
        return None

    req_clone = copy.deepcopy(positive_tc.request)
    req_clone.path_params = mutated_params

    # Check for documented 404 response schema
    resp_schema: dict[str, Any] | None = None
    if isinstance(chunk.operation, dict):
        responses = chunk.operation.get("responses", {})
        if isinstance(responses, dict):
            resp_404 = responses.get("404")
            if isinstance(resp_404, dict):
                content = resp_404.get("content", {})
                if isinstance(content, dict):
                    app_json = content.get("application/json", {})
                    if isinstance(app_json, dict) and "schema" in app_json:
                        resp_schema = app_json["schema"]

    try:
        response = ResponseAssertion(
            status_code=404,
            headers={"Content-Type": "application/json"} if resp_schema else {},
            schema_shape=resp_schema,
        )
    except (ValidationError, ValueError):
        response = ResponseAssertion(status_code=404)

    new_tags = list(positive_tc.tags)
    for t in ["negative", "404", "not_found"]:
        if t not in new_tags:
            new_tags.append(t)

    return GeneratedTestCase(
        test_type="negative_not_found",
        operation_id=positive_tc.operation_id,
        description=f"[404] Resource not found - {positive_tc.operation_id}",
        request=req_clone,
        response=response,
        tags=new_tags,
        security=copy.deepcopy(positive_tc.security),
        security_schemes=copy.deepcopy(positive_tc.security_schemes),
    )


def generate_400_test_case(
    positive_tc: GeneratedTestCase,
    chunk: OperationChunk,
) -> GeneratedTestCase | None:
    """Generate a 400 Bad Request negative test case by violating the request body schema.

    Parameters
    ----------
    positive_tc : GeneratedTestCase
        The valid happy-path test case.
    chunk : OperationChunk
        OpenAPI operation chunk containing requestBody schema.

    Returns
    -------
    GeneratedTestCase | None
        400 test case instance, or None if bodiless, non-JSON, or schema is unconstrained.
    """
    if positive_tc.request.body is None:
        return None

    schema = RequestBodyMutator.get_json_schema(chunk)
    if schema is None:
        return None

    mutated_body = RequestBodyMutator.mutate_json_body(positive_tc.request.body, schema)
    if mutated_body is None:
        return None

    req_clone = copy.deepcopy(positive_tc.request)
    req_clone.body = mutated_body

    # Check for documented 400 response schema
    resp_schema: dict[str, Any] | None = None
    if isinstance(chunk.operation, dict):
        responses = chunk.operation.get("responses", {})
        if isinstance(responses, dict):
            resp_400 = responses.get("400")
            if isinstance(resp_400, dict):
                content = resp_400.get("content", {})
                if isinstance(content, dict):
                    app_json = content.get("application/json", {})
                    if isinstance(app_json, dict) and "schema" in app_json:
                        resp_schema = app_json["schema"]

    try:
        response = ResponseAssertion(
            status_code=400,
            headers={"Content-Type": "application/json"} if resp_schema else {},
            schema_shape=resp_schema,
        )
    except (ValidationError, ValueError):
        response = ResponseAssertion(status_code=400)

    new_tags = list(positive_tc.tags)
    for t in ["negative", "400", "invalid_input"]:
        if t not in new_tags:
            new_tags.append(t)

    return GeneratedTestCase(
        test_type="negative_invalid_input",
        operation_id=positive_tc.operation_id,
        description=f"[400] Invalid input - {positive_tc.operation_id}",
        request=req_clone,
        response=response,
        tags=new_tags,
        security=copy.deepcopy(positive_tc.security),
        security_schemes=copy.deepcopy(positive_tc.security_schemes),
    )


def generate_negative_input_test_cases(
    positive_tc: GeneratedTestCase,
    chunk: OperationChunk,
    not_found: bool = True,
    invalid_input: bool = True,
) -> list[GeneratedTestCase]:
    """Generate 404 and 400 negative test cases as applicable.

    Preserves deterministic multiple sibling ordering:
    404 (negative_not_found) followed by 400 (negative_invalid_input).

    Parameters
    ----------
    positive_tc : GeneratedTestCase
        The valid happy-path test case.
    chunk : OperationChunk
        OpenAPI operation chunk.
    not_found : bool
        Whether to generate 404 Not Found test cases (defaults to True).
    invalid_input : bool
        Whether to generate 400 Bad Request test cases (defaults to True).

    Returns
    -------
    list[GeneratedTestCase]
        Ordered list of negative test cases.
    """
    cases: list[GeneratedTestCase] = []
    if not_found:
        case_404 = generate_404_test_case(positive_tc, chunk)
        if case_404 is not None:
            cases.append(case_404)
    if invalid_input:
        case_400 = generate_400_test_case(positive_tc, chunk)
        if case_400 is not None:
            cases.append(case_400)
    return cases
