"""OpenAPI structural diff engine and operation comparison logic."""

import re
from collections.abc import Generator
from pathlib import Path
from typing import Any

from specprobe.chunker.extractor import OperationExtractor
from specprobe.chunker.loader import load_openapi_spec
from specprobe.chunker.models import OperationChunk
from specprobe.diff.models import ChangeType, DiffChangeRecord, DiffSummary


def normalize_path_template(path: str) -> str:
    """Normalize OpenAPI path template by replacing parameter tokens with '{}'.

    Strips trailing slashes (unless root '/') and ensures a leading slash.

    Examples
    --------
    - '/pets/{petId}' -> '/pets/{}'
    - '/pets/{id}' -> '/pets/{}'
    - '/users/{userId}/posts/{postId}' -> '/users/{}/posts/{}'
    - '/pets/' -> '/pets'
    - '/' -> '/'
    """
    cleaned = path.strip()
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    if len(cleaned) > 1 and cleaned.endswith("/"):
        cleaned = cleaned.rstrip("/")

    # Replace parameter placeholders {paramName} with {}
    normalized = re.sub(r"\{[^}]+\}", "{}", cleaned)
    return normalized


def extract_spec_operations(
    spec_input: str | Path | dict[str, Any],
) -> tuple[dict[tuple[str, str], OperationChunk], dict[str, Any]]:
    """Load and normalize OpenAPI operations into a dictionary keyed by (method, normalized_path).

    Reuses chunker loader and extractor with schema_depth=None to retain complete nested
    schemas for structural diffing.
    """
    if isinstance(spec_input, (str, Path)):
        spec_dict = load_openapi_spec(spec_input)
    elif isinstance(spec_input, dict):
        spec_dict = spec_input
    else:
        raise TypeError(
            f"Expected str, Path, or dict for specification input, got {type(spec_input).__name__}"
        )

    extractor = OperationExtractor(spec_dict, schema_depth=None)
    # Disable pruner stderr emission during diff extraction
    extractor.pruner.emit_stderr = False

    operations: dict[tuple[str, str], OperationChunk] = {}
    for chunk in extractor.extract_operations():
        key = (chunk.metadata.method.upper(), normalize_path_template(chunk.metadata.path))
        operations[key] = chunk

    return operations, spec_dict


def resolve_schema(
    schema: dict[str, Any],
    components_schemas: dict[str, Any],
    visited: set[str] | None = None,
) -> dict[str, Any]:
    """Resolve $ref pointers and combine allOf definitions with circular reference guards."""
    if visited is None:
        visited = set()

    current = schema
    while isinstance(current, dict) and "$ref" in current:
        ref = current["$ref"]
        if not isinstance(ref, str) or ref in visited:
            break
        visited.add(ref)
        if ref.startswith("#/components/schemas/"):
            schema_name = ref.removeprefix("#/components/schemas/").split("/")[0]
            target = components_schemas.get(schema_name)
            if isinstance(target, dict):
                merged = dict(target)
                for k, v in current.items():
                    if k != "$ref":
                        merged[k] = v
                current = merged
            else:
                break
        else:
            break

    if isinstance(current, dict) and "allOf" in current and isinstance(current["allOf"], list):
        flattened = dict(current)
        combined_props = dict(current.get("properties", {}))
        combined_req = list(current.get("required", []))
        for sub in current["allOf"]:
            if isinstance(sub, dict):
                sub_resolved = resolve_schema(sub, components_schemas, set(visited))
                if "properties" in sub_resolved and isinstance(sub_resolved["properties"], dict):
                    combined_props.update(sub_resolved["properties"])
                if "required" in sub_resolved and isinstance(sub_resolved["required"], list):
                    for r in sub_resolved["required"]:
                        if r not in combined_req:
                            combined_req.append(r)
        flattened["properties"] = combined_props
        flattened["required"] = combined_req
        return flattened

    return current


class DiffEngine:
    """Deterministic structural diff engine comparing two OpenAPI specifications."""

    def __init__(
        self,
        old_spec: str | Path | dict[str, Any],
        new_spec: str | Path | dict[str, Any],
    ) -> None:
        self.old_ops, self.old_spec_dict = extract_spec_operations(old_spec)
        self.new_ops, self.new_spec_dict = extract_spec_operations(new_spec)
        self.old_components = self.old_spec_dict.get("components", {}).get("schemas", {})
        self.new_components = self.new_spec_dict.get("components", {}).get("schemas", {})
        self.summary = DiffSummary()

    def diff(self) -> Generator[DiffChangeRecord, None, None]:
        """Perform comparison and yield detected change records in deterministic order."""
        self.summary = DiffSummary()

        for record in self._diff_operations():
            self._update_summary(record)
            yield record

    def get_summary(self) -> DiffSummary:
        """Return the summary metrics after diff execution."""
        return self.summary

    def _update_summary(self, record: DiffChangeRecord) -> None:
        """Increment summary metrics based on the change record."""
        self.summary.total_changes += 1
        if record.breaking:
            self.summary.breaking_changes += 1

        if record.change_type == ChangeType.OPERATION_ADDED:
            self.summary.operations_added += 1
        elif record.change_type == ChangeType.OPERATION_REMOVED:
            self.summary.operations_removed += 1
        elif record.breaking:
            self.summary.schema_breaking_changes += 1

    def _diff_operations(self) -> Generator[DiffChangeRecord, None, None]:
        """Compare operations at the endpoint level and yield added/removed records."""
        old_keys = set(self.old_ops.keys())
        new_keys = set(self.new_ops.keys())

        # 1. Removed operations (breaking: true)
        removed_keys = sorted(old_keys - new_keys, key=lambda k: (k[1], k[0]))
        for key in removed_keys:
            chunk = self.old_ops[key]
            orig_path = chunk.metadata.path
            method = chunk.metadata.method.upper()
            yield DiffChangeRecord(
                change_type=ChangeType.OPERATION_REMOVED,
                breaking=True,
                method=method,
                path=orig_path,
                location=f"paths['{orig_path}'].{method.lower()}",
                description=f"Operation '{method} {orig_path}' was removed from specification.",
                old_value={
                    "operationId": chunk.metadata.operationId,
                    "summary": chunk.operation.get("summary"),
                },
                new_value=None,
            )

        # 2. Added operations (breaking: false)
        added_keys = sorted(new_keys - old_keys, key=lambda k: (k[1], k[0]))
        for key in added_keys:
            chunk = self.new_ops[key]
            orig_path = chunk.metadata.path
            method = chunk.metadata.method.upper()
            yield DiffChangeRecord(
                change_type=ChangeType.OPERATION_ADDED,
                breaking=False,
                method=method,
                path=orig_path,
                location=f"paths['{orig_path}'].{method.lower()}",
                description=f"Operation '{method} {orig_path}' was added in the new specification.",
                old_value=None,
                new_value={
                    "operationId": chunk.metadata.operationId,
                    "summary": chunk.operation.get("summary"),
                },
            )

        # 3. Shared operations (schema and response status diff)
        shared_keys = sorted(old_keys & new_keys, key=lambda k: (k[1], k[0]))
        for key in shared_keys:
            old_chunk = self.old_ops[key]
            new_chunk = self.new_ops[key]
            yield from self._diff_shared_operation(old_chunk, new_chunk)

    def _diff_shared_operation(
        self,
        old_chunk: OperationChunk,
        new_chunk: OperationChunk,
    ) -> Generator[DiffChangeRecord, None, None]:
        """Compare schemas and parameters for a shared operation."""
        method = old_chunk.metadata.method.upper()
        orig_path = old_chunk.metadata.path
        old_op = old_chunk.operation
        new_op = new_chunk.operation

        # 1. Parameter comparisons
        yield from self._diff_parameters(old_op, new_op, method, orig_path)

        # 2. Request body comparisons
        yield from self._diff_request_body(old_op, new_op, method, orig_path)

        # 3. Response comparisons (status code removals & schema differences)
        yield from self._diff_responses(old_op, new_op, method, orig_path)

    def _diff_parameters(
        self,
        old_op: dict[str, Any],
        new_op: dict[str, Any],
        method: str,
        orig_path: str,
    ) -> Generator[DiffChangeRecord, None, None]:
        """Diff parameters: check for newly required parameters and schema breaking changes."""
        old_params_raw = old_op.get("parameters", [])
        new_params_raw = new_op.get("parameters", [])

        old_params: dict[tuple[str, str], dict[str, Any]] = {}
        if isinstance(old_params_raw, list):
            for p in old_params_raw:
                if isinstance(p, dict) and "name" in p and "in" in p:
                    old_params[(p["in"], p["name"])] = p

        new_params: dict[tuple[str, str], dict[str, Any]] = {}
        if isinstance(new_params_raw, list):
            for p in new_params_raw:
                if isinstance(p, dict) and "name" in p and "in" in p:
                    new_params[(p["in"], p["name"])] = p

        # Check for newly required parameters
        for (param_in, param_name), new_p in sorted(new_params.items()):
            new_req = bool(new_p.get("required", False))
            old_p = old_params.get((param_in, param_name))
            old_req = bool(old_p.get("required", False)) if old_p else False

            if new_req and not old_req:
                yield DiffChangeRecord(
                    change_type=ChangeType.REQUIRED_REQUEST_PROPERTY_ADDED,
                    breaking=True,
                    method=method,
                    path=orig_path,
                    location=f"parameters[in='{param_in}',name='{param_name}'].required",
                    description=f"Parameter '{param_name}' in '{param_in}' is newly required.",
                    old_value=old_req,
                    new_value=True,
                )

        # Check shared parameter schema differences (types, enums, required properties)
        for param_in, param_name in sorted(set(old_params.keys()) & set(new_params.keys())):
            old_p = old_params[(param_in, param_name)]
            new_p = new_params[(param_in, param_name)]
            old_s = old_p.get("schema")
            new_s = new_p.get("schema")
            if isinstance(old_s, dict) and isinstance(new_s, dict):
                yield from self._diff_schemas(
                    old_schema=old_s,
                    new_schema=new_s,
                    location_prefix=f"parameters[in='{param_in}',name='{param_name}'].schema",
                    method=method,
                    orig_path=orig_path,
                    is_request=True,
                    is_response=False,
                )

    def _diff_request_body(
        self,
        old_op: dict[str, Any],
        new_op: dict[str, Any],
        method: str,
        orig_path: str,
    ) -> Generator[DiffChangeRecord, None, None]:
        """Diff request body: check if request body became required and diff content schemas."""
        old_rb = old_op.get("requestBody")
        new_rb = new_op.get("requestBody")

        old_rb_dict = old_rb if isinstance(old_rb, dict) else {}
        new_rb_dict = new_rb if isinstance(new_rb, dict) else {}

        # Check if requestBody became required
        old_req = bool(old_rb_dict.get("required", False))
        new_req = bool(new_rb_dict.get("required", False))
        if new_req and not old_req:
            yield DiffChangeRecord(
                change_type=ChangeType.REQUIRED_REQUEST_PROPERTY_ADDED,
                breaking=True,
                method=method,
                path=orig_path,
                location="requestBody.required",
                description="Request body is newly required.",
                old_value=old_req,
                new_value=True,
            )

        old_content = old_rb_dict.get("content", {})
        new_content = new_rb_dict.get("content", {})
        if isinstance(old_content, dict) and isinstance(new_content, dict):
            for media_type in sorted(set(old_content.keys()) & set(new_content.keys())):
                old_s = old_content[media_type].get("schema")
                new_s = new_content[media_type].get("schema")
                if isinstance(old_s, dict) and isinstance(new_s, dict):
                    yield from self._diff_schemas(
                        old_schema=old_s,
                        new_schema=new_s,
                        location_prefix=f"requestBody.content['{media_type}'].schema",
                        method=method,
                        orig_path=orig_path,
                        is_request=True,
                        is_response=False,
                    )

    def _diff_responses(
        self,
        old_op: dict[str, Any],
        new_op: dict[str, Any],
        method: str,
        orig_path: str,
    ) -> Generator[DiffChangeRecord, None, None]:
        """Diff responses: report removed 2xx status codes and diff response schemas."""
        old_resps_raw = old_op.get("responses", {})
        new_resps_raw = new_op.get("responses", {})

        old_resps = old_resps_raw if isinstance(old_resps_raw, dict) else {}
        new_resps = new_resps_raw if isinstance(new_resps_raw, dict) else {}

        # Rule 3: response_status_removed for 2xx status codes only
        removed_statuses = sorted(set(old_resps.keys()) - set(new_resps.keys()), key=str)
        for status in removed_statuses:
            status_str = str(status)
            if status_str.startswith("2") and len(status_str) == 3 and status_str.isdigit():
                yield DiffChangeRecord(
                    change_type=ChangeType.RESPONSE_STATUS_REMOVED,
                    breaking=True,
                    method=method,
                    path=orig_path,
                    location=f"responses['{status_str}']",
                    description=f"Success response status code '{status_str}' was removed.",
                    old_value=old_resps[status],
                    new_value=None,
                )

        # Diff schemas for shared status codes
        for status in sorted(set(old_resps.keys()) & set(new_resps.keys()), key=str):
            status_str = str(status)
            old_r = old_resps[status]
            new_r = new_resps[status]
            if not isinstance(old_r, dict) or not isinstance(new_r, dict):
                continue

            old_content = old_r.get("content", {})
            new_content = new_r.get("content", {})
            if isinstance(old_content, dict) and isinstance(new_content, dict):
                for media_type in sorted(set(old_content.keys()) & set(new_content.keys())):
                    old_s = old_content[media_type].get("schema")
                    new_s = new_content[media_type].get("schema")
                    if isinstance(old_s, dict) and isinstance(new_s, dict):
                        yield from self._diff_schemas(
                            old_schema=old_s,
                            new_schema=new_s,
                            location_prefix=f"responses['{status_str}'].content['{media_type}'].schema",
                            method=method,
                            orig_path=orig_path,
                            is_request=False,
                            is_response=True,
                        )

    def _diff_schemas(
        self,
        old_schema: dict[str, Any],
        new_schema: dict[str, Any],
        location_prefix: str,
        method: str,
        orig_path: str,
        is_request: bool,
        is_response: bool,
        visited_schemas: set[tuple[Any, Any]] | None = None,
    ) -> Generator[DiffChangeRecord, None, None]:
        """Recursively diff two schemas with cycle guards."""
        if visited_schemas is None:
            visited_schemas = set()

        old_key = (
            old_schema["$ref"]
            if isinstance(old_schema, dict) and "$ref" in old_schema
            else id(old_schema)
        )
        new_key = (
            new_schema["$ref"]
            if isinstance(new_schema, dict) and "$ref" in new_schema
            else id(new_schema)
        )
        pair_key = (old_key, new_key)

        if pair_key in visited_schemas:
            return
        visited_schemas.add(pair_key)

        old_resolved = resolve_schema(old_schema, self.old_components)
        new_resolved = resolve_schema(new_schema, self.new_components)

        # Rule 4: type_changed
        old_type = old_resolved.get("type")
        new_type = new_resolved.get("type")
        if old_type is not None and new_type is not None and old_type != new_type:
            yield DiffChangeRecord(
                change_type=ChangeType.TYPE_CHANGED,
                breaking=True,
                method=method,
                path=orig_path,
                location=f"{location_prefix}.type",
                description=f"Field declared type changed from '{old_type}' to '{new_type}'.",
                old_value=old_type,
                new_value=new_type,
            )

        # Rule 5: enum_value_removed
        old_enum = old_resolved.get("enum")
        new_enum = new_resolved.get("enum")
        if isinstance(old_enum, list) and isinstance(new_enum, list):
            removed_enums = [v for v in old_enum if v not in new_enum]
            if removed_enums:
                yield DiffChangeRecord(
                    change_type=ChangeType.ENUM_VALUE_REMOVED,
                    breaking=True,
                    method=method,
                    path=orig_path,
                    location=f"{location_prefix}.enum",
                    description=f"Allowable enum value(s) {removed_enums} were removed.",
                    old_value=old_enum,
                    new_value=new_enum,
                )

        # Rule 1: required_request_property_added (Request schemas only)
        if is_request:
            old_req = set(old_resolved.get("required", []))
            new_req = set(new_resolved.get("required", []))
            newly_required = sorted(new_req - old_req)
            for prop in newly_required:
                yield DiffChangeRecord(
                    change_type=ChangeType.REQUIRED_REQUEST_PROPERTY_ADDED,
                    breaking=True,
                    method=method,
                    path=orig_path,
                    location=f"{location_prefix}.required",
                    description=f"Property '{prop}' is newly required in request schema.",
                    old_value=list(old_req),
                    new_value=list(new_req),
                )

        # Rule 2: response_property_removed (Response schemas only)
        if is_response:
            old_props = old_resolved.get("properties")
            new_props = new_resolved.get("properties")
            if isinstance(old_props, dict) and isinstance(new_props, dict):
                removed_props = sorted(set(old_props.keys()) - set(new_props.keys()))
                for prop in removed_props:
                    yield DiffChangeRecord(
                        change_type=ChangeType.RESPONSE_PROPERTY_REMOVED,
                        breaking=True,
                        method=method,
                        path=orig_path,
                        location=f"{location_prefix}.properties.{prop}",
                        description=f"Property '{prop}' was removed from response schema.",
                        old_value=old_props[prop],
                        new_value=None,
                    )

        # Recursive traversal: properties
        old_props = old_resolved.get("properties")
        new_props = new_resolved.get("properties")
        if isinstance(old_props, dict) and isinstance(new_props, dict):
            for prop in sorted(set(old_props.keys()) & set(new_props.keys())):
                old_p_schema = old_props[prop]
                new_p_schema = new_props[prop]
                if isinstance(old_p_schema, dict) and isinstance(new_p_schema, dict):
                    yield from self._diff_schemas(
                        old_schema=old_p_schema,
                        new_schema=new_p_schema,
                        location_prefix=f"{location_prefix}.properties.{prop}",
                        method=method,
                        orig_path=orig_path,
                        is_request=is_request,
                        is_response=is_response,
                        visited_schemas=visited_schemas,
                    )

        # Recursive traversal: items (for array schemas)
        old_items = old_resolved.get("items")
        new_items = new_resolved.get("items")
        if isinstance(old_items, dict) and isinstance(new_items, dict):
            yield from self._diff_schemas(
                old_schema=old_items,
                new_schema=new_items,
                location_prefix=f"{location_prefix}.items",
                method=method,
                orig_path=orig_path,
                is_request=is_request,
                is_response=is_response,
                visited_schemas=visited_schemas,
            )
