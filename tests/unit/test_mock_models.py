"""Unit tests for mock server Pydantic models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from specprobe.mock.models import (
    MockAccessLogEntry,
    MockResponse,
    MockRoute,
    MockServerConfig,
)


def test_mock_response_defaults() -> None:
    """Test that MockResponse applies default empty headers and body."""
    response = MockResponse(status_code=204)
    assert response.status_code == 204
    assert response.headers == {}
    assert response.body == b""


def test_mock_response_with_body() -> None:
    """Test MockResponse with explicit headers and body bytes."""
    response = MockResponse(
        status_code=200,
        headers={"Content-Type": "application/json"},
        body=b'{"id": 0, "name": ""}',
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/json"
    assert response.body == b'{"id": 0, "name": ""}'


def test_mock_response_status_code_out_of_range() -> None:
    """Test that status codes outside 100-599 raise ValidationError."""
    with pytest.raises(ValidationError):
        MockResponse(status_code=999)
    with pytest.raises(ValidationError):
        MockResponse(status_code=99)


def test_mock_route_valid() -> None:
    """Test standard valid MockRoute instantiation."""
    route = MockRoute(
        method="GET",
        path="/pets/42",
        operation_id="showPetById",
        response=MockResponse(status_code=200),
        tags=["pets", "store"],
    )
    assert route.method == "GET"
    assert route.path == "/pets/42"
    assert route.operation_id == "showPetById"
    assert route.tags == ["pets", "store"]


def test_mock_route_missing_required_fields() -> None:
    """Test that MockRoute requires method, path, operation_id, and response."""
    with pytest.raises(ValidationError):
        MockRoute.model_validate({"method": "GET", "path": "/pets"})


def test_mock_server_config_defaults() -> None:
    """Test MockServerConfig default host and port."""
    config = MockServerConfig(input_source="tests/fixtures/generated_tests.jsonl")
    assert config.host == "127.0.0.1"
    assert config.port == 8000
    assert config.input_source == "tests/fixtures/generated_tests.jsonl"


def test_mock_server_config_custom() -> None:
    """Test MockServerConfig with custom host, port, and Path input_source."""
    config = MockServerConfig(host="0.0.0.0", port=9090, input_source=Path("cases.jsonl"))
    assert config.host == "0.0.0.0"
    assert config.port == 9090
    assert config.input_source == Path("cases.jsonl")


def test_mock_server_config_port_out_of_range() -> None:
    """Test that ports outside 1-65535 raise ValidationError."""
    with pytest.raises(ValidationError):
        MockServerConfig(input_source="-", port=0)
    with pytest.raises(ValidationError):
        MockServerConfig(input_source="-", port=70000)


def test_mock_server_config_stdin_source() -> None:
    """Test MockServerConfig accepts '-' as the stdin sentinel input_source."""
    config = MockServerConfig(input_source="-")
    assert config.input_source == "-"


def test_mock_access_log_entry() -> None:
    """Test MockAccessLogEntry field values and matched flag."""
    from datetime import UTC, datetime

    entry = MockAccessLogEntry(
        timestamp=datetime.now(UTC),
        method="GET",
        path="/pets",
        status_code=200,
        latency_ms=1.2,
        matched=True,
    )
    assert entry.method == "GET"
    assert entry.status_code == 200
    assert entry.matched is True


def test_mock_access_log_entry_negative_latency_rejected() -> None:
    """Test that negative latency_ms raises ValidationError."""
    from datetime import UTC, datetime

    with pytest.raises(ValidationError):
        MockAccessLogEntry(
            timestamp=datetime.now(UTC),
            method="GET",
            path="/pets",
            status_code=200,
            latency_ms=-1.0,
            matched=True,
        )
