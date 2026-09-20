"""Unit tests for deterministic structural gap analyzer and critique prompt assembly."""

from pathlib import Path

import pytest

from specprobe.audit.analyzer import analyze_structural_gaps, build_audit_critique_prompt
from specprobe.audit.models import (
    ArtifactTestItem,
    CoverageGapSeverity,
    CoverageGapType,
)
from specprobe.audit.parser import parse_artifact
from specprobe.chunker.models import ChunkMetadata, OperationChunk

FIXTURES_DIR = Path("tests/fixtures")
POSTMAN_FIXTURE = FIXTURES_DIR / "audit_postman_collection.json"


def _build_sample_chunks() -> list[OperationChunk]:
    return [
        OperationChunk(
            operation={
                "operationId": "listPets",
                "summary": "List all pets",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer"},
                    }
                ],
                "responses": {
                    "200": {"description": "A paged array of pets"},
                    "500": {"description": "Unexpected error"},
                },
            },
            components={},
            metadata=ChunkMetadata(
                method="GET",
                path="/pets",
                operationId="listPets",
                tags=["pets"],
            ),
        ),
        OperationChunk(
            operation={
                "operationId": "showPetById",
                "summary": "Info for a specific pet",
                "parameters": [
                    {"name": "petId", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "responses": {
                    "200": {"description": "Expected response to a valid request"},
                    "404": {"description": "Pet not found"},
                },
            },
            components={},
            metadata=ChunkMetadata(
                method="GET",
                path="/pets/{petId}",
                operationId="showPetById",
                tags=["pets"],
            ),
        ),
        OperationChunk(
            operation={
                "operationId": "createPets",
                "summary": "Create a pet",
                "responses": {
                    "201": {"description": "Null response"},
                },
            },
            components={},
            metadata=ChunkMetadata(
                method="POST",
                path="/pets",
                operationId="createPets",
                tags=["pets"],
            ),
        ),
    ]


def test_analyze_structural_gaps_petstore() -> None:
    """Verify structural gap analysis against audit_postman_collection.json with known gaps."""
    chunks = _build_sample_chunks()
    items = parse_artifact(str(POSTMAN_FIXTURE))

    report = analyze_structural_gaps(chunks, items)

    # 3 spec operations, 2 are tested (listPets, showPetById), 1 is missing (createPets)
    assert report.total_spec_operations == 3
    assert report.covered_operations == 2
    assert report.operation_coverage_pct == pytest.approx(66.67, 0.1)

    # Status codes:
    # listPets: 200, 500 (2) -> tested: 200
    # showPetById: 200, 404 (2) -> tested: 200
    # createPets: 201 (1) -> tested: none
    # Total documented: 5, covered: 2
    assert report.total_documented_statuses == 5
    assert report.covered_documented_statuses == 2
    assert report.status_coverage_pct == pytest.approx(40.0, 0.1)

    # Check for missing operation gap
    missing_ops = [
        gap
        for critique in report.operation_critiques
        for gap in critique.gaps
        if gap.gap_type == CoverageGapType.MISSING_OPERATION
    ]
    assert len(missing_ops) == 1
    assert missing_ops[0].target == "createPets"
    assert missing_ops[0].severity == CoverageGapSeverity.CRITICAL

    # Check for missing status code gaps (500 for listPets, 404 for showPetById)
    missing_statuses = [
        gap
        for critique in report.operation_critiques
        for gap in critique.gaps
        if gap.gap_type == CoverageGapType.MISSING_STATUS_CODE
    ]
    missing_status_targets = {gap.target for gap in missing_statuses}
    assert "500" in missing_status_targets
    assert "404" in missing_status_targets

    # Check for missing parameter gap (limit for listPets)
    missing_params = [
        gap
        for critique in report.operation_critiques
        for gap in critique.gaps
        if gap.gap_type == CoverageGapType.MISSING_PARAMETER
    ]
    assert any(g.target == "limit" for g in missing_params)

    # Check for phantom test gap (/orphan/test)
    phantom_gaps = [
        gap
        for critique in report.operation_critiques
        for gap in critique.gaps
        if gap.gap_type == CoverageGapType.PHANTOM_TEST
    ]
    assert len(phantom_gaps) == 1
    assert "/orphan/test" in phantom_gaps[0].target


def test_build_audit_critique_prompt() -> None:
    """Verify construction of LLM critique prompt from chunk and matched tests."""
    chunks = _build_sample_chunks()
    chunk = chunks[0]  # listPets
    test_item = ArtifactTestItem(
        name="List pets test",
        method="GET",
        path="/pets",
        expected_status=200,
        has_property_assertions=True,
    )

    prompt = build_audit_critique_prompt(chunk, [test_item], [])
    assert "Operation: GET /pets" in prompt
    assert "listPets" in prompt
    assert "List pets test" in prompt
    assert "Expected Status: 200" in prompt
