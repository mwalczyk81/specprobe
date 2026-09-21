"""Unit tests for AWS Bedrock cloud opt-in verification and provider-aware endpoint routing."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from specprobe.generator.cache import DiskCache
from specprobe.generator.gateway import (
    DEFAULT_LOCAL_API_BASE,
    DEFAULT_LOCAL_MODEL,
    LLMGateway,
)
from tests.unit.generator.conftest import (
    SAMPLE_BEDROCK_MODEL,
    SAMPLE_BEDROCK_NOVA,
)


class TestBedrockCloudOptIn:
    """Validate SpecProbe Constitution Principle IV cloud opt-in enforcement for Bedrock."""

    def test_bedrock_without_region_raises_value_error(
        self,
        clean_aws_env: pytest.MonkeyPatch,
    ) -> None:
        """Bedrock models must be rejected with ValueError when no AWS region is set."""
        expected_msg = (
            f"Cloud model '{SAMPLE_BEDROCK_MODEL}' requires AWS_REGION or AWS_DEFAULT_REGION "
            "environment variable. Cloud providers are strictly opt-in per "
            "SpecProbe Constitution Principle IV."
        )
        with pytest.raises(ValueError, match=expected_msg):
            LLMGateway(model=SAMPLE_BEDROCK_MODEL)

    def test_bedrock_from_env_without_region_raises_value_error(
        self,
        clean_aws_env: pytest.MonkeyPatch,
    ) -> None:
        """Bedrock model from SPECPROBE_LLM_MODEL must also be rejected when no region is set."""
        clean_aws_env.setenv("SPECPROBE_LLM_MODEL", SAMPLE_BEDROCK_NOVA)
        expected_msg = (
            f"Cloud model '{SAMPLE_BEDROCK_NOVA}' requires AWS_REGION or AWS_DEFAULT_REGION "
            "environment variable. Cloud providers are strictly opt-in per "
            "SpecProbe Constitution Principle IV."
        )
        with pytest.raises(ValueError, match=expected_msg):
            LLMGateway()

    def test_bedrock_with_aws_region_succeeds(
        self,
        clean_aws_env: pytest.MonkeyPatch,
    ) -> None:
        """Setting AWS_REGION satisfies cloud opt-in validation."""
        clean_aws_env.setenv("AWS_REGION", "us-east-1")
        gateway = LLMGateway(model=SAMPLE_BEDROCK_MODEL)
        assert gateway.model == SAMPLE_BEDROCK_MODEL

    def test_bedrock_with_aws_default_region_succeeds(
        self,
        clean_aws_env: pytest.MonkeyPatch,
    ) -> None:
        """Setting AWS_DEFAULT_REGION satisfies cloud opt-in validation."""
        clean_aws_env.setenv("AWS_DEFAULT_REGION", "us-west-2")
        gateway = LLMGateway(model=SAMPLE_BEDROCK_NOVA)
        assert gateway.model == SAMPLE_BEDROCK_NOVA

    def test_bedrock_case_insensitive_prefix(
        self,
        clean_aws_env: pytest.MonkeyPatch,
    ) -> None:
        """Model prefix matching for bedrock/ must be case-insensitive."""
        upper_model = "BEDROCK/anthropic.claude-3-5-sonnet-20241022-v2:0"
        with pytest.raises(ValueError, match="Cloud providers are strictly opt-in"):
            LLMGateway(model=upper_model)


class TestBedrockApiBaseResolution:
    """Validate provider-aware api_base resolution for Bedrock and backward-compatibility."""

    def test_bedrock_api_base_default_is_none(
        self,
        aws_region_env: pytest.MonkeyPatch,
    ) -> None:
        """Default api_base for Bedrock models must resolve to None, not localhost."""
        gateway = LLMGateway(model=SAMPLE_BEDROCK_MODEL)
        assert gateway.api_base is None

    def test_bedrock_explicit_api_base_preserved(
        self,
        aws_region_env: pytest.MonkeyPatch,
    ) -> None:
        """Explicitly passed api_base for Bedrock (e.g. Aitrium proxy) must be preserved."""
        proxy_url = "https://aitrium.internal.proxy/v1"
        gateway = LLMGateway(model=SAMPLE_BEDROCK_MODEL, api_base=proxy_url)
        assert gateway.api_base == proxy_url

    def test_bedrock_api_base_from_env_preserved(
        self,
        aws_region_env: pytest.MonkeyPatch,
    ) -> None:
        """SPECPROBE_LLM_API_BASE environment variable must be honored for Bedrock."""
        proxy_url = "https://aitrium.internal.proxy/v1"
        aws_region_env.setenv("SPECPROBE_LLM_API_BASE", proxy_url)
        gateway = LLMGateway(model=SAMPLE_BEDROCK_MODEL)
        assert gateway.api_base == proxy_url

    def test_local_model_default_api_base_preserved(
        self,
        clean_aws_env: pytest.MonkeyPatch,
    ) -> None:
        """Local models must continue defaulting to http://localhost:1234/v1."""
        gateway = LLMGateway(model=DEFAULT_LOCAL_MODEL)
        assert gateway.api_base == DEFAULT_LOCAL_API_BASE

    def test_default_gateway_api_base_preserved(
        self,
        clean_aws_env: pytest.MonkeyPatch,
    ) -> None:
        """Calling LLMGateway() with no args must continue defaulting to http://localhost:1234/v1."""
        gateway = LLMGateway()
        assert gateway.api_base == DEFAULT_LOCAL_API_BASE


class TestBedrockCompletionAndCaching:
    """Validate litellm.completion dispatch and cryptographic disk cache with Bedrock."""

    def test_bedrock_complete_passes_none_api_base(
        self,
        aws_region_env: pytest.MonkeyPatch,
        mock_bedrock_completion: MagicMock,
    ) -> None:
        """When api_base is None, complete() passes api_base=None to litellm.completion."""
        gateway = LLMGateway(model=SAMPLE_BEDROCK_MODEL)
        messages = [{"role": "user", "content": "Generate test"}]

        with patch("litellm.completion", return_value=mock_bedrock_completion) as mock_complete:
            res = gateway.complete(messages)
            assert "operation_id" in res
            mock_complete.assert_called_once()
            call_kwargs = mock_complete.call_args[1]
            assert call_kwargs["model"] == SAMPLE_BEDROCK_MODEL
            assert call_kwargs["api_base"] is None
            assert call_kwargs["messages"] == messages

    def test_bedrock_complete_passes_explicit_api_base(
        self,
        aws_region_env: pytest.MonkeyPatch,
        mock_bedrock_completion: MagicMock,
    ) -> None:
        """When explicit api_base is given, complete() forwards it to litellm.completion."""
        proxy_url = "https://aitrium.internal.proxy/v1"
        gateway = LLMGateway(model=SAMPLE_BEDROCK_MODEL, api_base=proxy_url)
        messages = [{"role": "user", "content": "Generate test"}]

        with patch("litellm.completion", return_value=mock_bedrock_completion) as mock_complete:
            gateway.complete(messages)
            assert mock_complete.call_args[1]["api_base"] == proxy_url

    def test_bedrock_disk_cache_record_and_replay(
        self,
        aws_region_env: pytest.MonkeyPatch,
        mock_bedrock_completion: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Bedrock completions must persist with api_base: null and replay deterministically."""
        cache = DiskCache(cache_dir=tmp_path)
        gateway = LLMGateway(model=SAMPLE_BEDROCK_MODEL)
        messages = [{"role": "user", "content": "Generate test for op"}]

        # First call: cache miss, calls litellm
        with patch("litellm.completion", return_value=mock_bedrock_completion) as mock_complete:
            res1 = gateway.complete(messages, cache=cache)
            assert mock_complete.call_count == 1
            assert res1 == '{"operation_id": "testOp", "test_type": "positive"}'

        # Inspect persisted cache file on disk
        cache_files = list(tmp_path.glob("*.json"))
        assert len(cache_files) == 1
        record = json.loads(cache_files[0].read_text(encoding="utf-8"))
        assert record["model"] == SAMPLE_BEDROCK_MODEL
        assert record["api_base"] is None  # Persisted as null in JSON

        # Second call: cache hit, zero litellm calls
        err_msg = "Should not be called"
        with patch("litellm.completion", side_effect=AssertionError(err_msg)) as mock_fail:
            res2 = gateway.complete(messages, cache=cache)
            assert res2 == res1
            mock_fail.assert_not_called()

    def test_bedrock_runtime_error_on_failure(
        self,
        aws_region_env: pytest.MonkeyPatch,
    ) -> None:
        """Remote completion failures for Bedrock must raise RuntimeError, not ConnectionError."""
        gateway = LLMGateway(model=SAMPLE_BEDROCK_MODEL)
        messages = [{"role": "user", "content": "Generate test"}]

        with patch("litellm.completion", side_effect=Exception("AWS Bedrock AccessDenied")):
            with pytest.raises(RuntimeError, match="LLM completion call failed for model"):
                gateway.complete(messages)
