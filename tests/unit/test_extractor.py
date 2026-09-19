"""Unit tests for OperationExtractor parameter merging, security, and operationId synthesis."""

from pathlib import Path

from specprobe.chunker.extractor import OperationExtractor
from specprobe.chunker.loader import load_openapi_spec


def test_path_parameter_inheritance(valid_openapi_30_path: Path) -> None:
    """Ensure path-level parameters are inherited by child operations."""
    spec = load_openapi_spec(valid_openapi_30_path)
    extractor = OperationExtractor(spec)
    chunks = list(extractor.extract_operations())

    # Find GET /pets/{petId}
    pet_chunk = next(
        c for c in chunks if c.metadata.path == "/pets/{petId}" and c.metadata.method == "GET"
    )
    params = pet_chunk.operation.get("parameters", [])
    pet_id_param = next((p for p in params if p.get("name") == "petId"), None)

    assert pet_id_param is not None
    assert pet_id_param["in"] == "path"
    assert pet_id_param["required"] is True


def test_operation_parameter_override(composition_31_path: Path) -> None:
    """Ensure operation-level parameter overrides path-level parameter matching name and in."""
    spec = load_openapi_spec(composition_31_path)
    extractor = OperationExtractor(spec)
    chunks = list(extractor.extract_operations())

    post_chunk = next(
        c for c in chunks if c.metadata.path == "/items/{itemId}" and c.metadata.method == "POST"
    )
    params = post_chunk.operation.get("parameters", [])

    # Both itemId and X-Trace-Id should be present
    assert len([p for p in params if p.get("name") == "X-Trace-Id"]) == 1
    trace_param = next(p for p in params if p.get("name") == "X-Trace-Id")
    # Operation-level defined required=True
    assert trace_param["required"] is True
    assert "Operation level override" in trace_param.get("description", "")


def test_security_inheritance(valid_openapi_30_path: Path) -> None:
    """Ensure global security is inherited unless explicitly overridden or disabled."""
    spec = load_openapi_spec(valid_openapi_30_path)
    extractor = OperationExtractor(spec)
    chunks = list(extractor.extract_operations())

    # /pets GET omits security -> inherits global apiKeyAuth
    list_pets = next(c for c in chunks if c.metadata.operationId == "listPets")
    assert list_pets.metadata.security == [{"apiKeyAuth": []}]

    # /pets/{petId} GET defines security: [] -> explicitly empty
    show_pet = next(c for c in chunks if c.metadata.operationId == "showPetById")
    assert show_pet.metadata.security == []


def test_operation_id_synthesis(valid_openapi_30_path: Path) -> None:
    """Ensure missing operationId is synthesized deterministically."""
    spec = load_openapi_spec(valid_openapi_30_path)
    extractor = OperationExtractor(spec)
    chunks = list(extractor.extract_operations())

    # DELETE /pets/{petId} has no operationId in the spec
    delete_pet = next(
        c for c in chunks if c.metadata.path == "/pets/{petId}" and c.metadata.method == "DELETE"
    )
    assert delete_pet.metadata.operationId == "delete_pets_pet_id"
    assert delete_pet.metadata.deprecated is True
