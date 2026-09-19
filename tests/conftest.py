"""Global pytest fixtures and configuration for SpecProbe tests."""

from pathlib import Path
import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the absolute Path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def valid_openapi_30_path(fixtures_dir: Path) -> Path:
    """Return the path to the valid OpenAPI 3.0 YAML fixture."""
    return fixtures_dir / "valid_openapi_30.yaml"


@pytest.fixture
def composition_31_path(fixtures_dir: Path) -> Path:
    """Return the path to the OpenAPI 3.1 composition JSON fixture."""
    return fixtures_dir / "composition_31.json"


@pytest.fixture
def circular_spec_path(fixtures_dir: Path) -> Path:
    """Return the path to the circular references YAML fixture."""
    return fixtures_dir / "circular_spec.yaml"


@pytest.fixture
def swagger_20_path(fixtures_dir: Path) -> Path:
    """Return the path to the legacy Swagger 2.0 JSON fixture."""
    return fixtures_dir / "swagger_20.json"


@pytest.fixture
def external_ref_spec_path(fixtures_dir: Path) -> Path:
    """Return the path to the external reference YAML fixture."""
    return fixtures_dir / "external_ref_spec.yaml"


@pytest.fixture
def large_public_spec_path(fixtures_dir: Path) -> Path:
    """Return the path to the large public spec fixture (official Stripe OpenAPI 3.0 spec)."""
    return fixtures_dir / "large_public_spec.json"


@pytest.fixture
def deep_chain_spec_path(fixtures_dir: Path) -> Path:
    """Return the path to the deep schema chain YAML fixture."""
    return fixtures_dir / "deep_chain_spec.yaml"

