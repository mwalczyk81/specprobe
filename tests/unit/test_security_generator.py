"""Unit tests for generator prompt construction and security metadata propagation."""

import json

from specprobe.chunker.models import ChunkMetadata, OperationChunk
from specprobe.generator.engine import GenerationEngine
from specprobe.generator.prompt import PromptBuilder


def test_prompt_builder_includes_security_requirements() -> None:
    """Verify PromptBuilder formats security requirements into the user prompt."""
    chunk = OperationChunk(
        metadata=ChunkMetadata(
            path="/secure/pets",
            method="GET",
            operationId="getSecurePets",
            security=[{"bearerAuth": ["read:pets"]}],
        ),
        operation={
            "summary": "Get secure pets",
            "responses": {"200": {"description": "OK"}},
        },
        components={
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                }
            }
        },
    )

    user_prompt = PromptBuilder.build_user_prompt(chunk)
    assert "Security Requirements:" in user_prompt
    assert "bearerAuth" in user_prompt

    system_prompt = PromptBuilder.build_system_prompt()
    assert (
        "credential placeholder" in system_prompt.lower()
        or "authorization" in system_prompt.lower()
    )


def test_engine_populates_security_metadata_and_ensures_placeholder() -> None:
    """Verify GenerationEngine populates security fields and ensures credential placeholder."""
    chunk = OperationChunk(
        metadata=ChunkMetadata(
            path="/secure/pets",
            method="GET",
            operationId="getSecurePets",
            security=[{"bearerAuth": []}],
        ),
        operation={
            "summary": "Get secure pets",
            "responses": {"200": {"description": "OK"}},
        },
        components={
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                }
            }
        },
    )

    raw_completion = json.dumps(
        {
            "operation_id": "getSecurePets",
            "description": "Fetch secure pets",
            "request": {
                "headers": {"Accept": "application/json"},
                "query_params": {},
                "path_params": {},
            },
            "response": {
                "status_code": 200,
                "headers": {"Content-Type": "application/json"},
                "schema_shape": None,
            },
            "tags": ["pets"],
        }
    )

    engine = GenerationEngine()
    test_case = engine._validate_completion(raw_completion, chunk)

    # Verify metadata fields are populated
    assert test_case.security == [{"bearerAuth": []}]
    assert "bearerAuth" in test_case.security_schemes

    # Verify credential placeholder is ensured in request headers
    assert "Authorization" in test_case.request.headers
    assert test_case.request.headers["Authorization"] == "Bearer <token>"
