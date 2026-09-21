"""Shared pytest fixtures and helpers for Bedrock LLM gateway tests."""

from collections.abc import Generator
from unittest.mock import MagicMock

import pytest

SAMPLE_BEDROCK_MODEL = "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"
SAMPLE_BEDROCK_NOVA = "bedrock/amazon.nova-pro-v1:0"


@pytest.fixture
def clean_aws_env(monkeypatch: pytest.MonkeyPatch) -> Generator[pytest.MonkeyPatch, None, None]:
    """Ensure AWS region and credential environment variables are unset."""
    for key in (
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "SPECPROBE_LLM_MODEL",
        "SPECPROBE_LLM_API_BASE",
    ):
        monkeypatch.delenv(key, raising=False)
    yield monkeypatch


@pytest.fixture
def aws_region_env(clean_aws_env: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Provide an isolated environment with AWS_REGION configured."""
    clean_aws_env.setenv("AWS_REGION", "us-east-1")
    return clean_aws_env


@pytest.fixture
def mock_bedrock_completion() -> MagicMock:
    """Return a mock LiteLLM completion response object."""
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"operation_id": "testOp", "test_type": "positive"}'
    mock_response.choices = [mock_choice]
    return mock_response
