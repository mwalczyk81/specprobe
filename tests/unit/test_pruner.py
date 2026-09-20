"""Unit tests for SchemaPruner with visited-set cycle detection."""

from pathlib import Path
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from specprobe.chunker.loader import load_openapi_spec
from specprobe.chunker.pruner import SchemaPruner


def test_prune_unreferenced_schemas(valid_openapi_30_path: Path) -> None:
    """Ensure unreferenced schemas (like UnusedSchema) are pruned from operation components."""
    spec = load_openapi_spec(valid_openapi_30_path)
    op = spec["paths"]["/pets"]["get"]
    all_schemas = spec.get("components", {}).get("schemas", {})

    pruner = SchemaPruner(all_schemas)
    pruned = pruner.prune_for_operation(op)

    # Pet and Error are reachable from /pets GET
    assert "Pet" in pruned
    assert "Error" in pruned
    # UnusedSchema and NewPet are not reachable from /pets GET
    assert "UnusedSchema" not in pruned
    assert "NewPet" not in pruned


def test_prune_polymorphic_compositions(composition_31_path: Path) -> None:
    """Ensure allOf, oneOf, anyOf branches are transitively gathered."""
    spec = load_openapi_spec(composition_31_path)
    op = spec["paths"]["/items/{itemId}"]["post"]
    all_schemas = spec.get("components", {}).get("schemas", {})

    pruner = SchemaPruner(all_schemas)
    pruned = pruner.prune_for_operation(op)

    assert "CompositePayload" in pruned
    assert "BaseEntity" in pruned
    assert "Cat" in pruned
    assert "Dog" in pruned
    assert "CompositeResponse" in pruned
    assert "Metadata" in pruned
    # OrphanedSchema must not be included
    assert "OrphanedSchema" not in pruned


def test_prune_circular_references(circular_spec_path: Path) -> None:
    """Ensure self-referencing and mutual circular references terminate safely."""
    spec = load_openapi_spec(circular_spec_path)
    all_schemas = spec.get("components", {}).get("schemas", {})

    # Self-referencing Node
    tree_op = spec["paths"]["/trees"]["get"]
    pruner_tree = SchemaPruner(all_schemas)
    pruned_tree = pruner_tree.prune_for_operation(tree_op)

    assert "Node" in pruned_tree
    assert "UnrelatedNode" not in pruned_tree
    # Verify local pointer is retained in Node schema
    node_schema = pruned_tree["Node"]
    assert node_schema["properties"]["parent"]["$ref"] == "#/components/schemas/Node"

    # Mutual circular User <-> Team
    user_op = spec["paths"]["/users/{userId}"]["get"]
    pruner_user = SchemaPruner(all_schemas)
    pruned_user = pruner_user.prune_for_operation(user_op)

    assert "User" in pruned_user
    assert "Team" in pruned_user
    assert "UnrelatedNode" not in pruned_user


def test_prune_depth_capping_default(deep_chain_spec_path: Path) -> None:
    """Ensure traversal terminates at default depth 2, retaining bare $ref and emitting warning."""
    spec = load_openapi_spec(deep_chain_spec_path)
    all_schemas = spec.get("components", {}).get("schemas", {})
    op = spec["paths"]["/chain"]["get"]

    pruner = SchemaPruner(all_schemas, max_depth=2)
    pruned = pruner.prune_for_operation(op)

    # Depth 1 (Level1) and Depth 2 (Level2) are included
    assert "Level1" in pruned
    assert "Level2" in pruned
    # Depth 3 (Level3) and Depth 4 (Level4) are truncated
    assert "Level3" not in pruned
    assert "Level4" not in pruned

    # Bare $ref pointer preserved in Level2 parent schema
    assert pruned["Level2"]["properties"]["next"]["$ref"] == "#/components/schemas/Level3"

    # Warning naming truncated schema and its depth
    assert len(pruner.warnings) == 1
    assert (
        "Schema 'Level3' at depth 3 exceeds schema depth limit of 2 and was truncated."
        in pruner.warnings[0]
    )


def test_prune_depth_capping_custom_depth(deep_chain_spec_path: Path) -> None:
    """Ensure configurable max_depth allows deeper expansion or shallower cutoff."""
    spec = load_openapi_spec(deep_chain_spec_path)
    all_schemas = spec.get("components", {}).get("schemas", {})
    op = spec["paths"]["/chain"]["get"]

    # max_depth = 4: expands all 4 levels without truncation
    pruner_deep = SchemaPruner(all_schemas, max_depth=4)
    pruned_deep = pruner_deep.prune_for_operation(op)
    assert {"Level1", "Level2", "Level3", "Level4"} <= set(pruned_deep.keys())
    assert pruner_deep.warnings == []

    # max_depth = 1: truncates at Level2 (depth 2)
    pruner_shallow = SchemaPruner(all_schemas, max_depth=1)
    pruned_shallow = pruner_shallow.prune_for_operation(op)
    assert "Level1" in pruned_shallow
    assert "Level2" not in pruned_shallow
    assert len(pruner_shallow.warnings) == 1
    assert (
        "Schema 'Level2' at depth 2 exceeds schema depth limit of 1 and was truncated."
        in pruner_shallow.warnings[0]
    )


@st.composite
def schema_graph_strategy(draw: st.DrawFn) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Generate arbitrary component schemas (including self-referential and cyclic graphs),
    an operation referencing a subset of those schemas, and a max_depth limit.
    """
    schema_names = draw(
        st.lists(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=6),
            min_size=1,
            max_size=8,
            unique=True,
        )
    )

    schemas: dict[str, Any] = {}
    for name in schema_names:
        num_refs = draw(st.integers(min_value=0, max_value=3))
        ref_targets = draw(
            st.lists(st.sampled_from(schema_names), min_size=num_refs, max_size=num_refs)
        )
        props: dict[str, Any] = {}
        for idx, target in enumerate(ref_targets):
            props[f"field_{idx}"] = {"$ref": f"#/components/schemas/{target}"}
        schemas[name] = {"type": "object", "properties": props}

    op_num_refs = draw(st.integers(min_value=0, max_value=3))
    op_targets = draw(
        st.lists(st.sampled_from(schema_names), min_size=op_num_refs, max_size=op_num_refs)
    )
    op_responses: dict[str, Any] = {}
    for idx, target in enumerate(op_targets):
        op_responses[f"20{idx}"] = {
            "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{target}"}}}
        }
    operation = {"responses": op_responses}

    max_depth = draw(st.integers(min_value=0, max_value=5))
    return schemas, operation, max_depth


@given(schema_graph_strategy())
def test_hypothesis_pruner_termination_depth_and_idempotency(
    graph_input: tuple[dict[str, Any], dict[str, Any], int],
) -> None:
    """Property test verifying that SchemaPruner:
    1. Always terminates on arbitrary (including cyclic) graphs.
    2. Never includes schemas deeper than max_depth.
    3. Is strictly idempotent across repeated pruning runs.
    """
    schemas, operation, max_depth = graph_input
    pruner1 = SchemaPruner(components_schemas=schemas, max_depth=max_depth, emit_stderr=False)
    pruned1 = pruner1.prune_for_operation(operation)

    # 1. Termination & Validity
    assert isinstance(pruned1, dict)
    for k in pruned1:
        assert k in schemas

    # 2. Depth constraint check via BFS
    initial_refs: set[str] = set()
    pruner1._extract_refs_from_node(operation, initial_refs)
    initial_names = {
        ref[len(SchemaPruner.SCHEMA_PREFIX) :].split("/")[0]
        for ref in initial_refs
        if ref.startswith(SchemaPruner.SCHEMA_PREFIX)
    }

    depths: dict[str, int] = {}
    q: list[tuple[str, int]] = [(name, 1) for name in initial_names if name in schemas]
    while q:
        curr, d = q.pop(0)
        if curr in depths and depths[curr] <= d:
            continue
        depths[curr] = d
        child_refs: set[str] = set()
        pruner1._extract_refs_from_node(schemas[curr], child_refs)
        for cr in child_refs:
            if cr.startswith(SchemaPruner.SCHEMA_PREFIX):
                cname = cr[len(SchemaPruner.SCHEMA_PREFIX) :].split("/")[0]
                if cname in schemas and (cname not in depths or depths[cname] > d + 1):
                    q.append((cname, d + 1))

    for name in pruned1:
        assert depths[name] <= max_depth, (
            f"Schema '{name}' has depth {depths[name]} which exceeds max_depth {max_depth}"
        )

    # 3. Idempotency
    pruner2 = SchemaPruner(components_schemas=schemas, max_depth=max_depth, emit_stderr=False)
    pruned2 = pruner2.prune_for_operation(operation)
    assert pruned1 == pruned2

    pruner3 = SchemaPruner(components_schemas=pruned1, max_depth=max_depth, emit_stderr=False)
    pruned3 = pruner3.prune_for_operation(operation)
    assert pruned1 == pruned3
