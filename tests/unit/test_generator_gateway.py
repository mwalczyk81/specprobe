"""Unit tests for LLMGateway configuration resolution and opt-in security."""

from unittest.mock import MagicMock, patch

import pytest

from specprobe.generator.gateway import (
    DEFAULT_LOCAL_API_BASE,
    DEFAULT_LOCAL_MODEL,
    LLMGateway,
    is_local_endpoint,
)


def test_is_local_endpoint() -> None:
    """Verify detection of localhost, private IPs, dev hosts, and remote URLs."""
    # Loopback
    assert is_local_endpoint("http://localhost:1234/v1")
    assert is_local_endpoint("http://127.0.0.1:8000/v1")
    assert is_local_endpoint("http://0.0.0.0:11434")

    # RFC 1918 private ranges
    assert is_local_endpoint("http://192.168.1.50:1234/v1")
    assert is_local_endpoint("http://10.0.0.5:8000/v1")
    assert is_local_endpoint("http://172.16.0.2:11434/v1")

    # Tailscale CGNAT range
    assert is_local_endpoint("http://100.64.1.2:1234/v1")

    # Known dev and local domains
    assert is_local_endpoint("http://host.docker.internal:1234/v1")
    assert is_local_endpoint("http://my-mac.local:1234/v1")
    assert is_local_endpoint("http://myserver.internal:1234/v1")

    # Scheme-less host:port inputs
    assert is_local_endpoint("localhost:1234/v1")
    assert is_local_endpoint("localhost:1234")
    assert is_local_endpoint("host.docker.internal:1234/v1")

    # Genuinely remote cloud URLs
    assert not is_local_endpoint("https://api.openai.com/v1")
    assert not is_local_endpoint("https://api.anthropic.com")
    assert not is_local_endpoint("https://generativelanguage.googleapis.com")
    assert not is_local_endpoint("http://8.8.8.8:1234/v1")
    assert not is_local_endpoint(None)


def test_non_loopback_private_endpoint_with_openai_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-loopback private endpoint (e.g. LAN LM Studio) must not require OPENAI_API_KEY."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    gateway = LLMGateway(
        model="openai/local-model",
        api_base="http://192.168.1.50:1234/v1",
    )
    assert gateway.api_key == "lm-studio"
    assert gateway.api_base == "http://192.168.1.50:1234/v1"

    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"operation_id": "test"}'
    mock_response.choices = [mock_choice]

    with patch("litellm.completion", return_value=mock_response) as mock_complete:
        res = gateway.complete([{"role": "user", "content": "hello"}])
        assert res == '{"operation_id": "test"}'
        assert mock_complete.call_args[1]["api_base"] == "http://192.168.1.50:1234/v1"


def test_custom_cloud_endpoint_preserves_api_base() -> None:
    """Explicit api_base for custom cloud routes must be passed through to litellm.completion."""
    gateway = LLMGateway(
        model="gpt-4o",
        api_base="https://custom-proxy.example.com/v1",
        api_key="sk-test-key",
    )

    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"operation_id": "test"}'
    mock_response.choices = [mock_choice]

    with patch("litellm.completion", return_value=mock_response) as mock_complete:
        res = gateway.complete([{"role": "user", "content": "hello"}])
        assert res == '{"operation_id": "test"}'
        assert mock_complete.call_args[1]["api_base"] == "https://custom-proxy.example.com/v1"


def test_default_initialization() -> None:
    """Default gateway must point to local LM Studio endpoint with dummy key."""
    gateway = LLMGateway()
    assert gateway.model == DEFAULT_LOCAL_MODEL
    assert gateway.api_base == DEFAULT_LOCAL_API_BASE
    assert gateway.api_key == "lm-studio"
    assert gateway.temperature == 0.0


def test_environment_variable_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variables should override defaults when CLI options omitted."""
    monkeypatch.setenv("SPECPROBE_LLM_MODEL", "openai/custom-local")
    monkeypatch.setenv("SPECPROBE_LLM_API_BASE", "http://127.0.0.1:5000/v1")
    monkeypatch.setenv("SPECPROBE_LLM_TEMPERATURE", "0.5")

    gateway = LLMGateway()
    assert gateway.model == "openai/custom-local"
    assert gateway.api_base == "http://127.0.0.1:5000/v1"
    assert gateway.temperature == 0.5


def test_cloud_opt_in_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Selecting cloud models without API keys must raise ValueError per Principle IV."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    # Remote OpenAI
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        LLMGateway(model="gpt-4o", api_base="https://api.openai.com/v1")

    # Remote Anthropic
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        LLMGateway(model="claude-3-5-sonnet", api_base="https://api.anthropic.com")

    # Remote Gemini
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        LLMGateway(
            model="gemini/gemini-2.5-flash", api_base="https://generativelanguage.googleapis.com"
        )


def test_completion_dispatch_success() -> None:
    """Verify completion dispatch extracts content from litellm response."""
    gateway = LLMGateway()

    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"operation_id": "test"}'
    mock_response.choices = [mock_choice]

    with patch("litellm.completion", return_value=mock_response) as mock_complete:
        result = gateway.complete([{"role": "user", "content": "hello"}])
        assert result == '{"operation_id": "test"}'
        assert mock_complete.called


def test_completion_dispatch_local_connection_error() -> None:
    """Verify local endpoint failure raises ConnectionError with helpful troubleshooting."""
    gateway = LLMGateway()

    with patch("litellm.completion", side_effect=Exception("Connection refused")):
        with pytest.raises(ConnectionError, match="Failed to connect to local model endpoint"):
            gateway.complete([{"role": "user", "content": "hello"}])
