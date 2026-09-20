"""Unit tests for security scheme extraction and pruning in OperationExtractor."""

import json
from pathlib import Path

import pytest

from specprobe.chunker.extractor import OperationExtractor

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "specs"


@pytest.fixture
def security_spec() -> dict:
    """Load the multi-scheme security test OpenAPI specification."""
    spec_path = FIXTURES_DIR / "security_schemes.json"
    with open(spec_path, encoding="utf-8") as f:
        return json.load(f)


def test_chunker_prunes_and_preserves_referenced_security_schemes(security_spec: dict) -> None:
    """Verify components contains only the security schemes referenced by the operation."""
    extractor = OperationExtractor(security_spec)
    chunks = {chunk.metadata.operationId: chunk for chunk in extractor.extract_operations()}

    # Bearer endpoint: only bearerAuth should be in components.securitySchemes
    bearer_chunk = chunks["getBearerResource"]
    assert bearer_chunk.metadata.security == [{"bearerAuth": []}]
    sec_schemes = bearer_chunk.components.get("securitySchemes", {})
    assert "bearerAuth" in sec_schemes
    assert sec_schemes["bearerAuth"]["type"] == "http"
    assert sec_schemes["bearerAuth"]["scheme"] == "bearer"
    # Verify pruning: basicAuth, apiKeyHeaderAuth, etc. must NOT be in components
    assert "basicAuth" not in sec_schemes
    assert "apiKeyHeaderAuth" not in sec_schemes


def test_chunker_compound_security_schemes(security_spec: dict) -> None:
    """Verify compound security operations include all referenced scheme definitions."""
    extractor = OperationExtractor(security_spec)
    chunks = {chunk.metadata.operationId: chunk for chunk in extractor.extract_operations()}

    compound_chunk = chunks["postCompoundSecurityResource"]
    sec_schemes = compound_chunk.components.get("securitySchemes", {})
    assert "apiKeyHeaderAuth" in sec_schemes
    assert "appIdAuth" in sec_schemes
    assert "bearerAuth" not in sec_schemes


def test_chunker_public_endpoint_omits_security_schemes(security_spec: dict) -> None:
    """Verify public endpoints with empty security have no security schemes in components."""
    extractor = OperationExtractor(security_spec)
    chunks = {chunk.metadata.operationId: chunk for chunk in extractor.extract_operations()}

    public_chunk = chunks["getPublicResource"]
    assert public_chunk.metadata.security == []
    sec_schemes = public_chunk.components.get("securitySchemes")
    assert not sec_schemes
