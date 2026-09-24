"""Unit tests for the deterministic JSON Schema Draft 7 mock payload synthesizer."""

from specprobe.mock.synth import synthesize_sample_from_schema


def test_synthesize_none_schema_returns_none() -> None:
    """Test that a None schema synthesizes to None."""
    assert synthesize_sample_from_schema(None) is None


def test_synthesize_string_type() -> None:
    """Test that a bare root string schema (no enclosing property) synthesizes to sample_value."""
    assert synthesize_sample_from_schema({"type": "string"}) == "sample_value"


def test_synthesize_string_format_is_honored() -> None:
    """Test that a recognized 'format' emits a valid representative literal, not ''."""
    assert (
        synthesize_sample_from_schema({"type": "string", "format": "date-time"})
        == "2024-01-01T00:00:00Z"
    )
    assert synthesize_sample_from_schema({"type": "string", "format": "date"}) == "2024-01-01"
    assert (
        synthesize_sample_from_schema({"type": "string", "format": "email"}) == "user@example.com"
    )
    assert (
        synthesize_sample_from_schema({"type": "string", "format": "uuid"})
        == "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    )
    assert (
        synthesize_sample_from_schema({"type": "string", "format": "uri"})
        == "https://example.com/sample"
    )
    assert (
        synthesize_sample_from_schema({"type": "string", "format": "url"})
        == "https://example.com/sample"
    )
    assert synthesize_sample_from_schema({"type": "string", "format": "ipv4"}) == "203.0.113.1"


def test_synthesize_string_unsupported_format_falls_back_to_key() -> None:
    """Test that an unrecognized 'format' falls back to the key-based sample value."""
    schema = {
        "type": "object",
        "required": ["hostname"],
        "properties": {"hostname": {"type": "string", "format": "hostname"}},
    }
    assert synthesize_sample_from_schema(schema) == {"hostname": "sample_hostname"}


def test_synthesize_format_aware_value_is_deterministic() -> None:
    """Test that repeated synthesis of the same format-aware node yields identical output."""
    schema = {"type": "string", "format": "date-time"}
    first = synthesize_sample_from_schema(schema)
    for _ in range(5):
        assert synthesize_sample_from_schema(schema) == first


def test_synthesize_integer_type_defaults_zero() -> None:
    """Test that a plain integer schema synthesizes to 0."""
    assert synthesize_sample_from_schema({"type": "integer"}) == 0


def test_synthesize_number_type_defaults_zero() -> None:
    """Test that a plain number schema synthesizes to 0."""
    assert synthesize_sample_from_schema({"type": "number"}) == 0


def test_synthesize_integer_honors_minimum() -> None:
    """Test that 'minimum' overrides the zero default to keep the value valid."""
    assert synthesize_sample_from_schema({"type": "integer", "minimum": 5}) == 5


def test_synthesize_boolean_type() -> None:
    """Test that a plain boolean schema synthesizes to False."""
    assert synthesize_sample_from_schema({"type": "boolean"}) is False


def test_synthesize_null_type() -> None:
    """Test that a null-typed schema synthesizes to None."""
    assert synthesize_sample_from_schema({"type": "null"}) is None


def test_synthesize_enum_uses_first_value() -> None:
    """Test that 'enum' takes precedence and returns the first listed value."""
    assert synthesize_sample_from_schema({"type": "string", "enum": ["dog", "cat"]}) == "dog"
    assert synthesize_sample_from_schema({"type": "integer", "enum": [7, 8]}) == 7


def test_synthesize_const_returns_literal() -> None:
    """Test that 'const' short-circuits type resolution and returns the literal."""
    assert synthesize_sample_from_schema({"type": "string", "const": "fixed"}) == "fixed"


def test_synthesize_object_required_only() -> None:
    """Test that only 'required' properties are included in synthesized objects."""
    schema = {
        "type": "object",
        "required": ["id", "name"],
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
            "tag": {"type": "string"},
        },
    }
    assert synthesize_sample_from_schema(schema) == {"id": 0, "name": "sample_name"}


def test_synthesize_object_no_required_returns_empty_dict() -> None:
    """Test that an object schema with no 'required' list synthesizes to {}."""
    schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}},
    }
    assert synthesize_sample_from_schema(schema) == {}


def test_synthesize_object_implicit_type_from_properties() -> None:
    """Test that 'type' is inferred as object when omitted but properties/required exist."""
    schema = {"required": ["id"], "properties": {"id": {"type": "integer"}}}
    assert synthesize_sample_from_schema(schema) == {"id": 0}


def test_synthesize_object_required_key_missing_from_properties() -> None:
    """Test that a required key absent from 'properties' still appears (as None)."""
    schema = {
        "type": "object",
        "required": ["id", "ghost"],
        "properties": {"id": {"type": "integer"}},
    }
    assert synthesize_sample_from_schema(schema) == {"id": 0, "ghost": None}


def test_synthesize_array_single_item() -> None:
    """Test that array schemas synthesize exactly one item."""
    schema = {"type": "array", "items": {"type": "integer"}}
    assert synthesize_sample_from_schema(schema) == [0]


def test_synthesize_array_no_items_returns_empty_list() -> None:
    """Test that an array schema with no 'items' synthesizes to []."""
    assert synthesize_sample_from_schema({"type": "array"}) == []


def test_synthesize_array_of_objects() -> None:
    """Test the exact petstore-style array-of-objects fixture shape."""
    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["id", "name"],
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "tag": {"type": "string"},
            },
        },
    }
    assert synthesize_sample_from_schema(schema) == [{"id": 0, "name": "sample_name"}]


def test_synthesize_resolves_local_defs_ref() -> None:
    """Test that a local '#/$defs/<name>' $ref is resolved against the root schema."""
    schema = {
        "type": "object",
        "required": ["pet"],
        "properties": {"pet": {"$ref": "#/$defs/Pet"}},
        "$defs": {
            "Pet": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "integer"}},
            }
        },
    }
    assert synthesize_sample_from_schema(schema) == {"pet": {"id": 0}}


def test_synthesize_resolves_local_definitions_ref() -> None:
    """Test that a local '#/definitions/<name>' $ref is resolved against the root schema."""
    schema = {
        "type": "array",
        "items": {"$ref": "#/definitions/Item"},
        "definitions": {"Item": {"type": "string"}},
    }
    assert synthesize_sample_from_schema(schema) == ["sample_value"]


def test_synthesize_unresolvable_ref_returns_none() -> None:
    """Test that an unresolvable local $ref falls back to None rather than raising."""
    schema = {"type": "object", "required": ["x"], "properties": {"x": {"$ref": "#/$defs/Missing"}}}
    assert synthesize_sample_from_schema(schema) == {"x": None}


def test_synthesize_different_keys_produce_different_sample_values() -> None:
    """Test that distinct plain string properties derive distinct values from their own keys."""
    schema = {
        "type": "object",
        "required": ["description", "notes"],
        "properties": {
            "description": {"type": "string"},
            "notes": {"type": "string"},
        },
    }
    assert synthesize_sample_from_schema(schema) == {
        "description": "sample_description",
        "notes": "sample_notes",
    }


def test_synthesize_array_item_inherits_enclosing_property_key() -> None:
    """Test that a plain-string array item inherits its enclosing object property's key."""
    schema = {
        "type": "object",
        "required": ["tags"],
        "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
    }
    assert synthesize_sample_from_schema(schema) == {"tags": ["sample_tags"]}


def test_synthesize_example_is_honored_regardless_of_type() -> None:
    """Test that a declared 'example' is returned verbatim regardless of node type."""
    assert synthesize_sample_from_schema({"type": "string", "example": "widget-42"}) == "widget-42"
    assert synthesize_sample_from_schema({"type": "integer", "example": 7}) == 7
    assert synthesize_sample_from_schema({"type": "object", "example": {"a": 1}}) == {"a": 1}
    assert synthesize_sample_from_schema({"type": "array", "example": [1, 2, 3]}) == [1, 2, 3]


def test_synthesize_default_is_honored_when_no_example() -> None:
    """Test that a declared 'default' is returned verbatim when 'example' is absent."""
    assert synthesize_sample_from_schema({"type": "string", "default": "WIDGET-STANDARD"}) == (
        "WIDGET-STANDARD"
    )
    assert synthesize_sample_from_schema({"type": "integer", "default": 7}) == 7


def test_synthesize_example_takes_precedence_over_default() -> None:
    """Test that 'example' wins when both 'example' and a different 'default' are declared."""
    schema = {"type": "string", "example": "from-example", "default": "from-default"}
    assert synthesize_sample_from_schema(schema) == "from-example"


def test_synthesize_const_and_enum_outrank_conflicting_example() -> None:
    """Test that 'const'/'enum' still win over a conflicting 'example' (FR-008)."""
    assert synthesize_sample_from_schema({"const": "fixed", "example": "not-fixed"}) == "fixed"
    assert synthesize_sample_from_schema({"enum": ["dog", "cat"], "example": "not-dog"}) == "dog"


def test_synthesize_example_on_container_replaces_entire_subtree() -> None:
    """Test that 'example' on an object/array node replaces the whole synthesized subtree."""
    schema = {
        "type": "object",
        "required": ["id", "name"],
        "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
        "example": {"id": 99, "name": "Widget"},
    }
    assert synthesize_sample_from_schema(schema) == {"id": 99, "name": "Widget"}


def test_synthesize_all_of_merges_properties_and_required() -> None:
    """Test that allOf branches contribute properties/required to the parent object,
    so required keys declared only in a branch resolve to real values, not None."""
    schema = {
        "type": "object",
        "required": ["accountType", "coreProductCode"],
        "allOf": [
            {"properties": {"accountType": {"enum": ["CD", "CHECKING"]}}},
            {
                "properties": {
                    "coreProductCode": {"type": "string", "maxLength": 10},
                    "id": {"type": "string"},
                },
                "required": ["id"],
            },
        ],
    }
    assert synthesize_sample_from_schema(schema) == {
        "accountType": "CD",
        "coreProductCode": "sample_cor",
        "id": "sample_id",
    }


def test_synthesize_all_of_resolves_local_ref_branches() -> None:
    """Test that a $ref inside allOf is resolved before merging."""
    schema = {
        "allOf": [{"$ref": "#/$defs/Base"}, {"required": ["name"]}],
        "$defs": {
            "Base": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "size": {"type": "integer"}},
                "required": ["size"],
            }
        },
    }
    assert synthesize_sample_from_schema(schema) == {"size": 0, "name": "sample_name"}


def test_synthesize_any_of_and_one_of_use_first_branch() -> None:
    """Test that anyOf/oneOf synthesize from their first alternative."""
    assert synthesize_sample_from_schema({"anyOf": [{"type": "integer"}, {"type": "string"}]}) == 0
    assert synthesize_sample_from_schema({"oneOf": [{"type": "boolean"}, {"type": "string"}]}) is (
        False
    )


def test_synthesize_string_honors_pattern() -> None:
    """Test that a string pattern the fallback value doesn't match is satisfied."""
    schema = {
        "type": "object",
        "required": ["currency", "ref"],
        "properties": {
            "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
            "ref": {"type": "string", "pattern": r"^(INV|PO)-\d{4}$"},
        },
    }
    assert synthesize_sample_from_schema(schema) == {"currency": "AAA", "ref": "INV-0000"}


def test_synthesize_string_pattern_already_matched_keeps_fallback() -> None:
    """Test that a pattern the default sample already satisfies leaves it unchanged."""
    schema = {"type": "string", "pattern": "^sample_"}
    assert synthesize_sample_from_schema(schema) == "sample_value"


def test_synthesize_string_unsupported_pattern_falls_back() -> None:
    """Test that a regex the sampler can't render falls back instead of raising."""
    schema = {"type": "string", "pattern": r"^(a)\1$"}
    assert synthesize_sample_from_schema(schema) == "sample_value"


def test_synthesize_string_fits_min_and_max_length() -> None:
    """Test that the fallback string is padded or truncated into the length bounds."""
    assert synthesize_sample_from_schema({"type": "string", "maxLength": 6}) == "sample"
    assert synthesize_sample_from_schema({"type": "string", "minLength": 15}) == "sample_valuexxx"
