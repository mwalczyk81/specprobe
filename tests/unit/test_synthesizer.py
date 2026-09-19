"""Unit tests for the natural-language operational document synthesizer."""

from specprobe.chunker.models import ChunkMetadata, OperationChunk
from specprobe.index.synthesizer import build_embedding_text


def test_synthesizer_basic_operation():
    """Verify clean synthesis of method, path, summary, description, and tags."""
    chunk = OperationChunk(
        metadata=ChunkMetadata(
            path="/pets",
            method="GET",
            operationId="listPets",
            tags=["pets", "animals"],
            source_title="Petstore API",
            source_version="1.0.0",
        ),
        operation={
            "operationId": "listPets",
            "summary": "List all pets",
            "description": "Returns a paginated list of pets from the system.",
            "tags": ["pets", "animals"],
        },
        components={},
    )
    text = build_embedding_text(chunk)
    assert text.startswith("GET /pets — List all pets")
    assert "Summary: List all pets" in text
    assert "Description: Returns a paginated list of pets from the system." in text
    assert "Tags: pets, animals" in text
    assert "{" not in text
    assert "}" not in text


def test_synthesizer_with_parameters_and_responses():
    """Verify parameters and responses are cleanly translated into natural language."""
    chunk = OperationChunk(
        metadata=ChunkMetadata(
            path="/pets/{petId}",
            method="GET",
            operationId="getPetById",
            tags=["pets"],
            source_title="Petstore API",
            source_version="1.0.0",
        ),
        operation={
            "operationId": "getPetById",
            "summary": "Find pet by ID",
            "description": "Returns a single pet.",
            "parameters": [
                {
                    "name": "petId",
                    "in": "path",
                    "required": True,
                    "description": "ID of pet to return",
                    "schema": {"type": "integer"},
                },
                {
                    "name": "detailed",
                    "in": "query",
                    "required": False,
                    "description": "Include medical history",
                    "schema": {"type": "boolean"},
                },
            ],
            "responses": {
                "200": {
                    "description": "Pet found successfully",
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Pet"}}
                    },
                },
                "404": {
                    "description": "Pet not found",
                },
            },
        },
        components={},
    )
    text = build_embedding_text(chunk)
    assert "Parameters:" in text
    assert "- petId (path, required): ID of pet to return (type: integer)" in text
    assert "- detailed (query, optional): Include medical history (type: boolean)" in text
    assert "Responses:" in text
    assert "- 200 (application/json): Pet found successfully (type: Pet)" in text
    assert "- 404: Pet not found" in text
    assert "$ref" not in text


def test_synthesizer_with_request_body():
    """Verify request body schema and descriptions are captured cleanly."""
    chunk = {
        "metadata": {
            "path": "/pets",
            "method": "POST",
            "operationId": "createPet",
            "tags": ["pets"],
        },
        "operation": {
            "operationId": "createPet",
            "summary": "Create a new pet",
            "requestBody": {
                "description": "Pet payload",
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/NewPet"}}
                },
            },
            "responses": {
                "201": {
                    "description": "Created",
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Pet"}}
                    },
                }
            },
        },
        "components": {},
    }
    text = build_embedding_text(chunk)
    assert "POST /pets — Create a new pet" in text
    assert "Request Body (application/json): Pet payload (type: NewPet)" in text
    assert "- 201 (application/json): Created (type: Pet)" in text
