"""Unit tests for MockServer HTTP request dispatch and lifecycle."""

import json
import socket
import threading
from collections.abc import Iterator
from http.client import HTTPConnection

import pytest

from specprobe.generator.models import GeneratedTestCase
from specprobe.mock.models import MockAccessLogEntry, MockServerConfig
from specprobe.mock.router import MockRouter
from specprobe.mock.server import MockServer, format_access_log_line


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _test_case(**overrides: object) -> GeneratedTestCase:
    payload = {
        "test_type": "positive",
        "operation_id": "listPets",
        "description": "List all pets",
        "request": {"method": "GET", "path": "/pets", "path_params": {}},
        "response": {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "schema_shape": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "integer"}},
            },
        },
    }
    payload.update(overrides)
    return GeneratedTestCase.model_validate(payload)


@pytest.fixture
def running_server() -> Iterator[MockServer]:
    router = MockRouter()
    router.load_test_cases(
        [
            _test_case(),
            _test_case(
                operation_id="createPets",
                request={"method": "POST", "path": "/pets", "path_params": {}},
                response={"status_code": 201, "headers": {}, "schema_shape": None},
            ),
            _test_case(
                operation_id="deletePet",
                request={
                    "method": "DELETE",
                    "path": "/pets/{petId}",
                    "path_params": {"petId": "42"},
                },
                response={"status_code": 204, "headers": {}, "schema_shape": None},
            ),
        ]
    )
    config = MockServerConfig(host="127.0.0.1", port=_free_port(), input_source="-")
    server = MockServer(config, router)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_matched_get_returns_status_and_body(running_server: MockServer) -> None:
    """Test that a matched GET request returns the canned status and synthesized body."""
    conn = HTTPConnection("127.0.0.1", running_server.server_port, timeout=5)
    conn.request("GET", "/pets")
    resp = conn.getresponse()
    body = resp.read()
    assert resp.status == 200
    assert json.loads(body) == {"id": 0}
    assert resp.getheader("Content-Type") == "application/json"
    assert resp.getheader("Content-Length") == str(len(body))
    conn.close()


def test_matched_post_returns_201(running_server: MockServer) -> None:
    """Test that a matched POST request returns 201 with empty body."""
    conn = HTTPConnection("127.0.0.1", running_server.server_port, timeout=5)
    conn.request("POST", "/pets", body=b'{"name":"Fido"}')
    resp = conn.getresponse()
    body = resp.read()
    assert resp.status == 201
    assert body == b""
    conn.close()


def test_matched_delete_returns_204_empty_body(running_server: MockServer) -> None:
    """Test that a matched DELETE request returns 204 with zero-byte body."""
    conn = HTTPConnection("127.0.0.1", running_server.server_port, timeout=5)
    conn.request("DELETE", "/pets/42")
    resp = conn.getresponse()
    body = resp.read()
    assert resp.status == 204
    assert body == b""
    assert resp.getheader("Content-Length") == "0"
    conn.close()


def test_query_parameters_are_ignored_for_matching(running_server: MockServer) -> None:
    """Test that query strings do not affect route matching."""
    conn = HTTPConnection("127.0.0.1", running_server.server_port, timeout=5)
    conn.request("GET", "/pets?limit=10&page=2")
    resp = conn.getresponse()
    body = resp.read()
    assert resp.status == 200
    assert json.loads(body) == {"id": 0}
    conn.close()


def test_custom_host_and_port_binding() -> None:
    """Test that MockServer binds to the host/port specified in MockServerConfig."""
    router = MockRouter()
    router.load_test_cases([_test_case()])
    config = MockServerConfig(host="127.0.0.1", port=_free_port(), input_source="-")
    server = MockServer(config, router)
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert server.server_port > 0
    finally:
        server.server_close()


def test_allow_reuse_address_enabled() -> None:
    """Test that allow_reuse_address is enabled for immediate socket reclamation."""
    assert MockServer.allow_reuse_address is True


def test_concurrent_requests_are_dispatched(running_server: MockServer) -> None:
    """Test that ThreadingHTTPServer services multiple concurrent connections."""
    results: list[int] = []
    lock = threading.Lock()

    def _make_request() -> None:
        conn = HTTPConnection("127.0.0.1", running_server.server_port, timeout=5)
        conn.request("GET", "/pets")
        resp = conn.getresponse()
        resp.read()
        with lock:
            results.append(resp.status)
        conn.close()

    threads = [threading.Thread(target=_make_request) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert results == [200] * 10


def test_shutdown_releases_socket_for_rebinding(running_server: MockServer) -> None:
    """Test that shutdown()+server_close() releases the port for immediate rebinding."""
    port = running_server.server_port
    running_server.shutdown()
    running_server.server_close()

    router = MockRouter()
    router.load_test_cases([_test_case()])
    config = MockServerConfig(host="127.0.0.1", port=port, input_source="-")
    new_server = MockServer(config, router)
    new_server.server_close()


def test_port_collision_raises_oserror() -> None:
    """Test that binding to a port already held by a non-reusable listener raises OSError."""
    occupier = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupier.bind(("127.0.0.1", 0))
    occupier.listen(1)
    occupied_port = occupier.getsockname()[1]
    try:
        router = MockRouter()
        router.load_test_cases([_test_case()])
        config = MockServerConfig(host="127.0.0.1", port=occupied_port, input_source="-")
        with pytest.raises(OSError):
            MockServer(config, router)
    finally:
        occupier.close()


def test_format_access_log_line_matched() -> None:
    """Test the concise access log line format for a matched request."""
    from datetime import UTC, datetime

    entry = MockAccessLogEntry(
        timestamp=datetime(2026, 9, 22, 12, 0, 1, tzinfo=UTC),
        method="GET",
        path="/pets",
        status_code=200,
        latency_ms=1.2,
        matched=True,
    )
    line = format_access_log_line(entry, "/pets?limit=10")
    assert line.startswith("[12:00:01] GET")
    assert "/pets?limit=10" in line
    assert "200" in line
    assert "(1.2ms)" in line
    assert "[UNMATCHED]" not in line


def test_format_access_log_line_unmatched() -> None:
    """Test that unmatched requests are flagged with [UNMATCHED]."""
    from datetime import UTC, datetime

    entry = MockAccessLogEntry(
        timestamp=datetime(2026, 9, 22, 12, 0, 4, tzinfo=UTC),
        method="GET",
        path="/unknown",
        status_code=404,
        latency_ms=0.4,
        matched=False,
    )
    line = format_access_log_line(entry, "/unknown")
    assert "[UNMATCHED]" in line
