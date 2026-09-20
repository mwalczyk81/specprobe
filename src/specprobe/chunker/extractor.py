"""OpenAPI operation extractor with parameter merging and operationId synthesis."""

import copy
import re
from collections.abc import Generator
from typing import Any

from specprobe.chunker.models import ChunkMetadata, OperationChunk
from specprobe.chunker.pruner import SchemaPruner
from specprobe.chunker.tokens import estimate_tokens

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head", "trace"}


class OperationExtractor:
    """Extracts, normalizes, and packages individual operations into autonomous chunks."""

    def __init__(self, spec: dict[str, Any], schema_depth: int = 2) -> None:
        self.spec = spec
        self.schema_depth = schema_depth
        self.global_security = spec.get("security", [])
        self.source_title = spec.get("info", {}).get("title", "Untitled API")
        self.source_version = spec.get("info", {}).get("version", "0.0.0")
        self.all_schemas = spec.get("components", {}).get("schemas", {})
        self.all_security_schemes = spec.get("components", {}).get("securitySchemes", {})
        self.pruner = SchemaPruner(self.all_schemas, max_depth=schema_depth)

        self.seen_operation_ids: set[str] = set()

    def _synthesize_operation_id(self, method: str, path: str) -> str:
        """Synthesize a unique, deterministic operationId from HTTP method and path."""
        # Convert camelCase like {petId} to {pet_id}
        snake_path = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", path)
        # Replace non-alphanumeric chars with underscores
        clean_path = re.sub(r"[^a-zA-Z0-9]+", "_", snake_path).strip("_").lower()
        base_id = f"{method.lower()}_{clean_path}" if clean_path else method.lower()

        candidate = base_id
        counter = 1
        while candidate in self.seen_operation_ids:
            counter += 1
            candidate = f"{base_id}_{counter}"

        self.seen_operation_ids.add(candidate)
        return candidate

    def _merge_parameters(
        self,
        path_params: list[dict[str, Any]],
        op_params: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge path-level parameters into operation parameters.

        Operation-level parameters take precedence over path-level parameters matching (name, in).
        """
        # Index operation parameters by (name, in)
        op_keys = {(p.get("name"), p.get("in")) for p in op_params if isinstance(p, dict)}

        merged = [copy.deepcopy(p) for p in op_params]
        for p in path_params:
            if isinstance(p, dict):
                key = (p.get("name"), p.get("in"))
                if key not in op_keys:
                    merged.append(copy.deepcopy(p))

        return merged

    def _resolve_security(self, op: dict[str, Any]) -> list[dict[str, list[str]]]:
        """Resolve security requirements for an operation.

        If operation explicitly declares 'security' (even if empty []), use it.
        Otherwise, fall back to global specification security.
        """
        if "security" in op:
            return copy.deepcopy(op["security"])
        return copy.deepcopy(self.global_security)

    def _prune_security_schemes(self, security: list[dict[str, list[str]]]) -> dict[str, Any]:
        """Prune components.securitySchemes to include only those referenced by the operation."""
        if not security or not self.all_security_schemes:
            return {}

        referenced_names: set[str] = set()
        for req in security:
            if isinstance(req, dict):
                referenced_names.update(req.keys())

        pruned: dict[str, Any] = {}
        for name in referenced_names:
            if name in self.all_security_schemes and isinstance(
                self.all_security_schemes[name], dict
            ):
                pruned[name] = copy.deepcopy(self.all_security_schemes[name])

        return pruned

    def extract_operations(self) -> Generator[OperationChunk, None, None]:
        """Iterate through all paths and operations, yielding an OperationChunk for each."""
        paths = self.spec.get("paths", {})
        if not isinstance(paths, dict):
            return

        for path_str, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            path_params = path_item.get("parameters", [])
            if not isinstance(path_params, list):
                path_params = []

            for method in sorted(HTTP_METHODS):
                if method not in path_item:
                    continue

                raw_op = path_item[method]
                if not isinstance(raw_op, dict):
                    continue

                op = copy.deepcopy(raw_op)

                # 1. Merge parameters
                op_params = op.get("parameters", [])
                if not isinstance(op_params, list):
                    op_params = []
                merged_params = self._merge_parameters(path_params, op_params)
                if merged_params:
                    op["parameters"] = merged_params
                elif "parameters" in op and not merged_params:
                    op["parameters"] = []

                # 2. Resolve operationId
                explicit_id = op.get("operationId")
                if explicit_id and isinstance(explicit_id, str) and explicit_id.strip():
                    operation_id = explicit_id.strip()
                    self.seen_operation_ids.add(operation_id)
                else:
                    operation_id = self._synthesize_operation_id(method, path_str)
                    op["operationId"] = operation_id

                # 3. Resolve security
                security = self._resolve_security(op)

                # 4. Prune referenced component schemas and security schemes
                pruned_schemas = self.pruner.prune_for_operation(op)
                pruned_security = self._prune_security_schemes(security)
                components_payload: dict[str, Any] = {}
                if pruned_schemas:
                    components_payload["schemas"] = pruned_schemas
                if pruned_security:
                    components_payload["securitySchemes"] = pruned_security

                # 5. Extract metadata attributes
                tags = op.get("tags", [])
                if not isinstance(tags, list):
                    tags = []
                deprecated = bool(op.get("deprecated", False))

                # Collect warnings
                warnings = list(self.pruner.warnings)

                # 6. Estimate tokens
                # Calculate tokens over the operation and pruned components
                chunk_dict_for_estimation = {
                    "operation": op,
                    "components": components_payload,
                }
                estimated_tokens = estimate_tokens(chunk_dict_for_estimation)

                metadata = ChunkMetadata(
                    path=path_str,
                    method=method.upper(),
                    tags=tags,
                    operationId=operation_id,
                    security=security,
                    deprecated=deprecated,
                    source_title=self.source_title,
                    source_version=self.source_version,
                    estimated_tokens=estimated_tokens,
                    warnings=warnings,
                )

                yield OperationChunk(
                    metadata=metadata,
                    operation=op,
                    components=components_payload,
                )
