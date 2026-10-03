"""Unit tests for OpenAPI structural diff engine."""

from typing import Any

from specprobe.diff.engine import DiffEngine, normalize_path_template
from specprobe.diff.models import ChangeType


def test_normalize_path_template() -> None:
    """Verify path template normalization replaces parameters and handles slashes."""
    assert normalize_path_template("/pets/{petId}") == "/pets/{}"
    assert normalize_path_template("/pets/{id}") == "/pets/{}"
    assert normalize_path_template("/users/{userId}/posts/{postId}") == "/users/{}/posts/{}"
    assert normalize_path_template("/pets/") == "/pets"
    assert normalize_path_template("pets") == "/pets"
    assert normalize_path_template("/") == "/"


def test_diff_operations_added_and_removed() -> None:
    """Verify operations present only in new spec are added, and only in old spec are removed."""
    old_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/pets": {
                "get": {
                    "summary": "List pets",
                    "responses": {"200": {"description": "OK"}},
                },
            },
            "/pets/{id}": {
                "delete": {
                    "summary": "Delete pet",
                    "parameters": [{"name": "id", "in": "path", "required": True}],
                    "responses": {"204": {"description": "No Content"}},
                },
            },
        },
    }

    new_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "2.0.0"},
        "paths": {
            "/pets": {
                "get": {
                    "summary": "List pets",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "summary": "Create pet",
                    "responses": {"201": {"description": "Created"}},
                },
            },
        },
    }

    engine = DiffEngine(old_spec=old_spec, new_spec=new_spec)
    records = list(engine.diff())

    assert len(records) == 2

    # Verify removed operation (breaking)
    removed = [r for r in records if r.change_type == ChangeType.OPERATION_REMOVED]
    assert len(removed) == 1
    assert removed[0].breaking is True
    assert removed[0].method == "DELETE"
    assert removed[0].path == "/pets/{id}"
    assert "DELETE /pets/{id}" in removed[0].description

    # Verify added operation (non-breaking)
    added = [r for r in records if r.change_type == ChangeType.OPERATION_ADDED]
    assert len(added) == 1
    assert added[0].breaking is False
    assert added[0].method == "POST"
    assert added[0].path == "/pets"
    assert "POST /pets" in added[0].description


def test_diff_operations_path_parameter_token_rename() -> None:
    """Verify renaming a path parameter token does not trigger false removals/additions."""
    old_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/pets/{petId}": {
                "get": {
                    "summary": "Get pet",
                    "parameters": [{"name": "petId", "in": "path", "required": True}],
                    "responses": {"200": {"description": "OK"}},
                },
            },
        },
    }

    new_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "2.0.0"},
        "paths": {
            "/pets/{id}": {
                "get": {
                    "summary": "Get pet",
                    "parameters": [{"name": "id", "in": "path", "required": True}],
                    "responses": {"200": {"description": "OK"}},
                },
            },
        },
    }

    engine = DiffEngine(old_spec=old_spec, new_spec=new_spec)
    records = list(engine.diff())

    op_changes = [
        r
        for r in records
        if r.change_type in (ChangeType.OPERATION_ADDED, ChangeType.OPERATION_REMOVED)
    ]
    assert len(op_changes) == 0


def test_diff_operations_operation_id_rename() -> None:
    """Verify changing operationId does not trigger operation addition or removal."""
    old_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/pets": {
                "get": {
                    "operationId": "listPetsLegacy",
                    "responses": {"200": {"description": "OK"}},
                },
            },
        },
    }

    new_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "2.0.0"},
        "paths": {
            "/pets": {
                "get": {
                    "operationId": "listPetsModern",
                    "responses": {"200": {"description": "OK"}},
                },
            },
        },
    }

    engine = DiffEngine(old_spec=old_spec, new_spec=new_spec)
    records = list(engine.diff())
    assert len(records) == 0


def test_diff_identical_specs() -> None:
    """Verify comparing identical specs produces zero change records."""
    spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/pets": {
                "get": {
                    "responses": {"200": {"description": "OK"}},
                },
            },
        },
    }

    engine = DiffEngine(old_spec=spec, new_spec=spec)
    records = list(engine.diff())
    assert len(records) == 0
    summary = engine.get_summary()
    assert summary.total_changes == 0
    assert summary.breaking_changes == 0
    assert summary.has_breaking_changes is False


def test_diff_schema_ref_resolution_and_cycle_guard() -> None:
    """Verify $ref pointers are resolved and recursive cycles terminate safely."""
    old_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Tree API", "version": "1.0.0"},
        "paths": {
            "/nodes": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/TreeNode"}
                                }
                            },
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "TreeNode": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "extra": {"type": "string"},
                        "child": {"$ref": "#/components/schemas/TreeNode"},
                    },
                }
            }
        },
    }

    new_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Tree API", "version": "2.0.0"},
        "paths": {
            "/nodes": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/TreeNode"}
                                }
                            },
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "TreeNode": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        # 'extra' removed (breaking)
                        "child": {"$ref": "#/components/schemas/TreeNode"},
                    },
                }
            }
        },
    }

    engine = DiffEngine(old_spec=old_spec, new_spec=new_spec)
    records = list(engine.diff())
    assert len(records) == 1
    assert records[0].change_type == ChangeType.RESPONSE_PROPERTY_REMOVED
    assert records[0].breaking is True
    assert "extra" in records[0].location


def test_diff_rule_1_required_request_property_added() -> None:
    """Verify newly required request body properties and parameters are detected as breaking."""
    old_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/items": {
                "post": {
                    "parameters": [
                        {
                            "name": "filter",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string"},
                        }
                    ],
                    "requestBody": {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["name"],
                                    "properties": {
                                        "name": {"type": "string"},
                                        "price": {"type": "number"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    new_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "2.0.0"},
        "paths": {
            "/items": {
                "post": {
                    "parameters": [
                        # 1. Existing parameter becomes required
                        {
                            "name": "filter",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        # 2. Brand new parameter is required
                        {
                            "name": "apiKey",
                            "in": "header",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                    ],
                    "requestBody": {
                        # 3. Request body itself becomes required
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    # 4. 'price' added to required array
                                    "required": ["name", "price"],
                                    "properties": {
                                        "name": {"type": "string"},
                                        "price": {"type": "number"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    engine = DiffEngine(old_spec=old_spec, new_spec=new_spec)
    records = list(engine.diff())

    required_changes = [
        r for r in records if r.change_type == ChangeType.REQUIRED_REQUEST_PROPERTY_ADDED
    ]
    assert len(required_changes) == 4
    for r in required_changes:
        assert r.breaking is True


def test_diff_rule_2_response_property_removed() -> None:
    """Verify removed response properties in shared status codes are detected as breaking."""
    old_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/items": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            "category": {"type": "string"},
                                            "meta": {
                                                "type": "object",
                                                "properties": {
                                                    "version": {"type": "string"},
                                                    "deprecated": {"type": "boolean"},
                                                },
                                            },
                                        },
                                    }
                                }
                            },
                        }
                    }
                }
            }
        },
    }

    new_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "2.0.0"},
        "paths": {
            "/items": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            # 'category' removed
                                            "meta": {
                                                "type": "object",
                                                "properties": {
                                                    "version": {"type": "string"},
                                                    # 'deprecated' removed from nested object
                                                },
                                            },
                                        },
                                    }
                                }
                            },
                        }
                    }
                }
            }
        },
    }

    engine = DiffEngine(old_spec=old_spec, new_spec=new_spec)
    records = list(engine.diff())

    removed_props = [r for r in records if r.change_type == ChangeType.RESPONSE_PROPERTY_REMOVED]
    assert len(removed_props) == 2
    for r in removed_props:
        assert r.breaking is True
    locations = [r.location for r in removed_props]
    assert any("category" in loc for loc in locations)
    assert any("deprecated" in loc for loc in locations)


def test_diff_rule_3_response_status_removed_2xx_only() -> None:
    """Verify removed 2xx status codes are reported as breaking; non-2xx are ignored."""
    old_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/items": {
                "post": {
                    "responses": {
                        "200": {"description": "OK"},
                        "204": {"description": "No Content"},
                        "404": {"description": "Not Found"},
                        "500": {"description": "Internal Error"},
                    }
                }
            }
        },
    }

    new_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "2.0.0"},
        "paths": {
            "/items": {
                "post": {
                    "responses": {
                        "201": {"description": "Created"},
                        # 200 and 204 removed (2xx breaking)
                        # 404 and 500 removed (non-2xx, non-breaking, ignored)
                    }
                }
            }
        },
    }

    engine = DiffEngine(old_spec=old_spec, new_spec=new_spec)
    records = list(engine.diff())

    status_removed = [r for r in records if r.change_type == ChangeType.RESPONSE_STATUS_REMOVED]
    assert len(status_removed) == 2
    statuses = [r.location for r in status_removed]
    assert any("200" in s for s in statuses)
    assert any("204" in s for s in statuses)
    assert not any("404" in s for s in statuses)
    assert not any("500" in s for s in statuses)


def test_diff_rule_4_type_changed() -> None:
    """Verify field data type changes in parameters, request bodies, and responses are breaking."""
    old_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/items/{id}": {
                "put": {
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "price": {"type": "number"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "active": {"type": "boolean"},
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
    }

    new_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "2.0.0"},
        "paths": {
            "/items/{id}": {
                "put": {
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        },
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "price": {"type": "integer"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "active": {"type": "string"},
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
    }

    engine = DiffEngine(old_spec=old_spec, new_spec=new_spec)
    records = list(engine.diff())

    type_changes = [r for r in records if r.change_type == ChangeType.TYPE_CHANGED]
    assert len(type_changes) == 3
    for r in type_changes:
        assert r.breaking is True


def test_diff_rule_5_enum_value_removed() -> None:
    """Verify removing allowable enum values is detected as breaking."""
    old_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/pets": {
                "get": {
                    "parameters": [
                        {
                            "name": "status",
                            "in": "query",
                            "schema": {
                                "type": "string",
                                "enum": ["available", "pending", "sold"],
                            },
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    new_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "2.0.0"},
        "paths": {
            "/pets": {
                "get": {
                    "parameters": [
                        {
                            "name": "status",
                            "in": "query",
                            "schema": {
                                "type": "string",
                                "enum": ["available", "sold"],  # 'pending' removed
                            },
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    engine = DiffEngine(old_spec=old_spec, new_spec=new_spec)
    records = list(engine.diff())

    enum_changes = [r for r in records if r.change_type == ChangeType.ENUM_VALUE_REMOVED]
    assert len(enum_changes) == 1
    assert enum_changes[0].breaking is True
    assert "pending" in enum_changes[0].description


def test_diff_non_breaking_exclusions() -> None:
    """Verify non-breaking edits (descriptions, optional fields, enums) are ignored."""
    old_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Store API", "version": "1.0.0", "description": "Old API description"},
        "paths": {
            "/items": {
                "post": {
                    "summary": "Old summary",
                    "description": "Old operation description",
                    "parameters": [
                        {
                            "name": "tag",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["a", "b"]},
                        }
                    ],
                    "requestBody": {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string", "example": "foo"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Item OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"id": {"type": "string"}},
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
    }

    new_spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {
            "title": "Store API",
            "version": "2.0.0",
            "description": "Completely new description",
        },
        "paths": {
            "/items": {
                "post": {
                    "summary": "Brand new summary",
                    "description": "Brand new operation description",
                    "parameters": [
                        # Enum value 'c' added (non-breaking)
                        {
                            "name": "tag",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["a", "b", "c"]},
                        },
                        # Optional parameter added (non-breaking)
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer"},
                        },
                    ],
                    "requestBody": {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string", "example": "bar"},
                                        # Optional request property added (non-breaking)
                                        "description": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Item OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            # Response property added (non-breaking)
                                            "createdAt": {"type": "string"},
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
    }

    engine = DiffEngine(old_spec=old_spec, new_spec=new_spec)
    records = list(engine.diff())
    assert len(records) == 0
