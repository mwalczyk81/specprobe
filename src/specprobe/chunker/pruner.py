"""Schema pruner for OpenAPI operations with visited-set cycle detection."""

import sys
from typing import Any


class SchemaPruner:
    """Traverses referenced schemas from an operation and prunes unused component schemas."""

    SCHEMA_PREFIX = "#/components/schemas/"

    def __init__(
        self,
        components_schemas: dict[str, Any] | None = None,
        max_depth: int | None = 2,
        emit_stderr: bool = True,
    ) -> None:
        self.all_schemas = components_schemas or {}
        self.max_depth = max_depth
        self.emit_stderr = emit_stderr
        self.warnings: list[str] = []
        self._emitted_stderr_warnings: set[str] = set()

    def _record_external_ref_warning(self, ref: str) -> None:
        """Record non-fatal external reference warning and write advisory warning to stderr."""
        warning_msg = f"External reference '{ref}' is unsupported and was preserved without expansion."
        if warning_msg not in self.warnings:
            self.warnings.append(warning_msg)
        if self.emit_stderr and warning_msg not in self._emitted_stderr_warnings:
            self._emitted_stderr_warnings.add(warning_msg)
            sys.stderr.write(f"Warning: {warning_msg}\n")
            sys.stderr.flush()

    def _extract_refs_from_node(self, node: Any, refs: set[str]) -> None:
        """Recursively traverse node to collect all $ref string values."""
        if isinstance(node, dict):
            for key, val in node.items():
                if key == "$ref" and isinstance(val, str):
                    refs.add(val)
                else:
                    self._extract_refs_from_node(val, refs)
        elif isinstance(node, list):
            for item in node:
                self._extract_refs_from_node(item, refs)

    def prune_for_operation(self, operation: dict[str, Any]) -> dict[str, Any]:
        """Collect and return component schemas transitively referenced by the operation up to max_depth.

        Uses a visited-set guard to handle circular and self-referencing schemas safely,
        terminating recursion at cycle boundaries while retaining local $ref pointers.
        When traversal would exceed max_depth, stops expanding that schema's nested refs:
        retaining bare $ref pointers without adding the target schema to components.schemas,
        and recording a warning in self.warnings naming the truncated schema and its depth.
        """
        self.warnings = []

        # 1. Collect all initial references from the operation payload
        initial_refs: set[str] = set()
        self._extract_refs_from_node(operation, initial_refs)

        # 2. Extract schema names and initialize queue at depth 1
        visited: set[str] = set()
        enqueued: set[str] = set()
        queue: list[tuple[str, int]] = []

        for ref in initial_refs:
            if ref.startswith(self.SCHEMA_PREFIX):
                schema_name = ref[len(self.SCHEMA_PREFIX):].split("/")[0]
                # Direct references from operation are at depth 1
                if self.max_depth is not None and 1 > self.max_depth:
                    warning_msg = (
                        f"Schema '{schema_name}' at depth 1 exceeds schema depth limit of {self.max_depth} and was truncated."
                    )
                    if warning_msg not in self.warnings:
                        self.warnings.append(warning_msg)
                else:
                    if schema_name not in enqueued:
                        enqueued.add(schema_name)
                        queue.append((schema_name, 1))
            elif not ref.startswith("#/"):
                self._record_external_ref_warning(ref)

        # 3. Transitive traversal with cycle detection and depth capping
        while queue:
            schema_name, depth = queue.pop(0)
            if schema_name in visited:
                continue  # Cycle detected; terminate recursion at cycle boundary

            visited.add(schema_name)

            if schema_name in self.all_schemas:
                schema_body = self.all_schemas[schema_name]
                child_refs: set[str] = set()
                self._extract_refs_from_node(schema_body, child_refs)

                for ref in child_refs:
                    if ref.startswith(self.SCHEMA_PREFIX):
                        child_name = ref[len(self.SCHEMA_PREFIX):].split("/")[0]
                        child_depth = depth + 1

                        if child_name in visited or child_name in enqueued:
                            # Already visited or already scheduled for inclusion at <= child_depth
                            continue

                        if self.max_depth is not None and child_depth > self.max_depth:
                            # Depth limit exceeded: retain bare $ref in parent, do not expand child
                            warning_msg = (
                                f"Schema '{child_name}' at depth {child_depth} exceeds "
                                f"schema depth limit of {self.max_depth} and was truncated."
                            )
                            if warning_msg not in self.warnings:
                                self.warnings.append(warning_msg)
                        else:
                            enqueued.add(child_name)
                            queue.append((child_name, child_depth))
                    elif not ref.startswith("#/"):
                        self._record_external_ref_warning(ref)

        # 4. Construct pruned dictionary
        pruned = {name: self.all_schemas[name] for name in visited if name in self.all_schemas}
        return pruned
