"""Unit tests for the deterministic JSON Schema Draft 7 mock payload synthesizer."""

from specprobe.mock.synth import synthesize_sample_from_schema


def test_synthesize_none_schema_returns_none() -> None:
    """Test that a None schema synthesizes to None."""
    assert synthesize_sample_from_schema(None) is None


def test_synthesize_string_type() -> None:
    """Test that a plain string schema synthesizes to an empty string."""
    assert synthesize_sample_from_schema({"type": "string"}) == ""


def test_synthesize_string_format_is_ignored() -> None:
    """Test that 'format' hints do not change the minimal string output."""
    assert synthesize_sample_from_schema({"type": "string", "format": "date-time"}) == ""
    assert synthesize_sample_from_schema({"type": "string", "format": "uuid"}) == ""


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
    assert synthesize_sample_from_schema(schema) == {"id": 0, "name": ""}


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
    assert synthesize_sample_from_schema(schema) == [{"id": 0, "name": ""}]


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
    assert synthesize_sample_from_schema(schema) == [""]


def test_synthesize_unresolvable_ref_returns_none() -> None:
    """Test that an unresolvable local $ref falls back to None rather than raising."""
    schema = {"type": "object", "required": ["x"], "properties": {"x": {"$ref": "#/$defs/Missing"}}}
    assert synthesize_sample_from_schema(schema) == {"x": None}
