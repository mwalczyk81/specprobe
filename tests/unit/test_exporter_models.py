"""Unit tests for exporter models and environment configurations."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from specprobe.exporter.models import ExportConfig, ExportEnvironment, ExportFormat
from specprobe.exporter.utils import sanitize_environment_filename


def test_export_environment_valid() -> None:
    """Test standard valid ExportEnvironment instantiation."""
    env = ExportEnvironment(
        name="  local  ",
        base_url="http://localhost:8000/ ",
        variables={"apiKey": "my-key"},
    )
    assert env.name == "local"
    assert env.base_url == "http://localhost:8000"
    assert env.variables == {"apiKey": "my-key"}


def test_export_environment_empty_name() -> None:
    """Test that empty or whitespace-only name raises ValidationError."""
    with pytest.raises(ValidationError):
        ExportEnvironment(name="   ", base_url="http://localhost:8000")


def test_export_environment_empty_base_url() -> None:
    """Test that empty or slash-only base_url raises ValidationError."""
    with pytest.raises(ValidationError):
        ExportEnvironment(name="dev", base_url="   ")


def test_export_environment_extra_fields_forbidden() -> None:
    """Test that extra fields on ExportEnvironment trigger validation error."""
    with pytest.raises(ValidationError):
        ExportEnvironment.model_validate(
            {"name": "dev", "base_url": "http://localhost:8000", "unexpected": "boom"}
        )


def test_export_config_with_environments() -> None:
    """Test ExportConfig populated with environments list."""
    env1 = ExportEnvironment(name="local", base_url="http://localhost:8000")
    env2 = ExportEnvironment(name="work", base_url="https://api.work.internal")
    config = ExportConfig(
        format=ExportFormat.BOTH,
        output_path=Path("./out"),
        environments=[env1, env2],
        env_file=Path("./env.yaml"),
    )
    assert len(config.environments) == 2
    assert config.environments[0].name == "local"
    assert config.environments[1].name == "work"
    assert config.env_file == Path("./env.yaml")


def test_export_config_extra_forbidden() -> None:
    """Test that extra fields on ExportConfig trigger validation error."""
    with pytest.raises(ValidationError):
        ExportConfig.model_validate({"extra_key": "not_allowed"})


def test_sanitize_environment_filename() -> None:
    """Test sanitization of environment names into safe filenames."""
    assert sanitize_environment_filename("local") == "local"
    assert sanitize_environment_filename("work/staging:v1") == "work_staging_v1"
    assert sanitize_environment_filename("  test  env  ") == "test_env"
    assert sanitize_environment_filename("???") == "environment"
    assert sanitize_environment_filename("") == "environment"
