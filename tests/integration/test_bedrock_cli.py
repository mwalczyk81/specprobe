"""Integration tests for specprobe generate and audit CLI commands with AWS Bedrock backend."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from specprobe.cli import cli

SAMPLE_BEDROCK_MODEL = "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"


def _mock_completion_response(content: str) -> MagicMock:
    """Create a mock LiteLLM completion response object."""
    mock_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp.choices = [mock_choice]
    return mock_resp


class TestGenerateBedrockCLI:
    """CLI integration tests for specprobe generate with Bedrock."""

    def test_generate_bedrock_without_region_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Invoking generate with a Bedrock model without AWS region must exit with error."""
        monkeypatch.delenv("AWS_REGION", raising=False)
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "generate",
                "tests/fixtures/search_full_results.json",
                "--model",
                SAMPLE_BEDROCK_MODEL,
            ],
        )

        assert result.exit_code != 0
        assert "requires AWS_REGION or AWS_DEFAULT_REGION" in result.output
        assert "SpecProbe Constitution Principle IV" in result.output

    def test_generate_bedrock_with_region_omits_api_base(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When AWS region is set, generate succeeds and omits api_base (passes None)."""
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        monkeypatch.delenv("SPECPROBE_LLM_API_BASE", raising=False)

        runner = CliRunner()
        mock_payload = json.dumps(
            {
                "operation_id": "listPets",
                "description": "Fetch pets",
                "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
                "response": {"status_code": 200, "headers": {}, "schema_shape": None},
                "tags": ["pets"],
            }
        )

        mock_resp = _mock_completion_response(mock_payload)
        with patch("litellm.completion", return_value=mock_resp) as mock_comp:
            result = runner.invoke(
                cli,
                [
                    "generate",
                    "tests/fixtures/search_full_results.json",
                    "--model",
                    SAMPLE_BEDROCK_MODEL,
                    "--no-cache",
                ],
            )

        assert result.exit_code == 0
        assert mock_comp.called
        # Verify that api_base was omitted (passed as None)
        assert mock_comp.call_args[1]["api_base"] is None
        assert mock_comp.call_args[1]["model"] == SAMPLE_BEDROCK_MODEL

    def test_generate_bedrock_with_explicit_api_base(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Explicit --api-base (e.g. Aitrium proxy) is forwarded to litellm.completion."""
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        proxy_url = "https://aitrium.internal.proxy/v1"

        runner = CliRunner()
        mock_payload = json.dumps(
            {
                "operation_id": "listPets",
                "description": "Fetch pets",
                "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
                "response": {"status_code": 200, "headers": {}, "schema_shape": None},
                "tags": ["pets"],
            }
        )

        mock_resp = _mock_completion_response(mock_payload)
        with patch("litellm.completion", return_value=mock_resp) as mock_comp:
            result = runner.invoke(
                cli,
                [
                    "generate",
                    "tests/fixtures/search_full_results.json",
                    "--model",
                    SAMPLE_BEDROCK_MODEL,
                    "--api-base",
                    proxy_url,
                    "--no-cache",
                ],
            )

        assert result.exit_code == 0
        assert mock_comp.call_args[1]["api_base"] == proxy_url


class TestAuditBedrockCLI:
    """CLI integration tests for specprobe audit with Bedrock."""

    def test_audit_bedrock_without_region_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Invoking audit with a Bedrock model without AWS region must exit with error."""
        monkeypatch.delenv("AWS_REGION", raising=False)
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "audit",
                "tests/fixtures/audit_postman_collection.json",
                "--spec",
                "tests/fixtures/valid_openapi_30.yaml",
                "--model",
                SAMPLE_BEDROCK_MODEL,
            ],
        )

        assert result.exit_code != 0
        assert "requires AWS_REGION or AWS_DEFAULT_REGION" in result.output
        assert "SpecProbe Constitution Principle IV" in result.output

    def test_audit_bedrock_with_region_omits_api_base(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When AWS region is set, audit succeeds with Bedrock model and omits api_base."""
        monkeypatch.setenv("AWS_REGION", "us-west-2")
        monkeypatch.delenv("SPECPROBE_LLM_API_BASE", raising=False)

        runner = CliRunner()
        mock_critique = json.dumps(
            {
                "operation_id": "listPets",
                "assertion_quality_score": 0.8,
                "critique_summary": "Assertions present.",
                "gaps": [],
            }
        )

        mock_resp = _mock_completion_response(mock_critique)
        with patch("litellm.completion", return_value=mock_resp) as mock_comp:
            result = runner.invoke(
                cli,
                [
                    "audit",
                    "tests/fixtures/audit_postman_collection.json",
                    "--spec",
                    "tests/fixtures/valid_openapi_30.yaml",
                    "--model",
                    SAMPLE_BEDROCK_MODEL,
                    "--no-cache",
                ],
            )

        assert result.exit_code == 0
        assert mock_comp.called
        assert mock_comp.call_args[1]["api_base"] is None
        assert mock_comp.call_args[1]["model"] == SAMPLE_BEDROCK_MODEL

    def test_audit_bedrock_with_explicit_api_base(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Explicit --api-base for audit is forwarded to litellm.completion."""
        monkeypatch.setenv("AWS_REGION", "us-west-2")
        proxy_url = "https://aitrium.internal.proxy/v1"

        runner = CliRunner()
        mock_critique = json.dumps(
            {
                "operation_id": "listPets",
                "assertion_quality_score": 0.8,
                "critique_summary": "Assertions present.",
                "gaps": [],
            }
        )

        mock_resp = _mock_completion_response(mock_critique)
        with patch("litellm.completion", return_value=mock_resp) as mock_comp:
            result = runner.invoke(
                cli,
                [
                    "audit",
                    "tests/fixtures/audit_postman_collection.json",
                    "--spec",
                    "tests/fixtures/valid_openapi_30.yaml",
                    "--model",
                    SAMPLE_BEDROCK_MODEL,
                    "--api-base",
                    proxy_url,
                    "--no-cache",
                ],
            )

        assert result.exit_code == 0
        assert mock_comp.call_args[1]["api_base"] == proxy_url
