"""Unit tests for SchemaPruner with visited-set cycle detection."""

from pathlib import Path

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
