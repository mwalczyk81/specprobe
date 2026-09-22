"""Integration tests for the `specprobe mock` CLI command."""

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from specprobe.cli import cli

FIXTURE = "tests/fixtures/generated_tests.jsonl"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_server(host: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"Server on {host}:{port} did not start in time") from last_error


class _MockServerProcess:
    def __init__(self, args: list[str]) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "specprobe.cli", "mock", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def stop(self) -> tuple[str, str]:
        self.proc.terminate()
        try:
            out, err = self.proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            out, err = self.proc.communicate(timeout=5)
        return out, err


@pytest.fixture
def spawn_mock_server() -> Iterator[type[_MockServerProcess]]:
    processes: list[_MockServerProcess] = []

    def _spawn(args: list[str]) -> _MockServerProcess:
        proc = _MockServerProcess(args)
        processes.append(proc)
        return proc

    yield _spawn
    for proc in processes:
        proc.stop()


def test_cli_mock_custom_port_and_host(spawn_mock_server) -> None:
    """Test that --port and --host bind the server to the requested address."""
    port = _free_port()
    server = spawn_mock_server([FIXTURE, "--port", str(port), "--host", "127.0.0.1"])
    _wait_for_server("127.0.0.1", port)

    with urllib.request.urlopen(f"http://127.0.0.1:{port}/pets", timeout=5) as resp:
        assert resp.status == 200
        assert json.loads(resp.read()) == [{"id": 0, "name": ""}]

    out, _ = server.stop()
    assert f"http://127.0.0.1:{port}" in out


def test_cli_mock_stdin_streaming() -> None:
    """Test that piping JSONL via '-' buffers input and serves the same routes."""
    port = _free_port()
    lines = Path(FIXTURE).read_text(encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "specprobe.cli", "mock", "-", "--port", str(port)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdin is not None
        proc.stdin.write(lines)
        proc.stdin.close()
        _wait_for_server("127.0.0.1", port)

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/pets/42", timeout=5) as resp:
            assert resp.status == 200
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        if proc.stdout is not None:
            proc.stdout.close()
        if proc.stderr is not None:
            proc.stderr.close()


def test_cli_mock_404_diagnostic(spawn_mock_server) -> None:
    """Test that an unmatched path returns 404 with a structured JSON diagnostic."""
    port = _free_port()
    spawn_mock_server([FIXTURE, "--port", str(port)])
    _wait_for_server("127.0.0.1", port)

    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/unknown/endpoint", timeout=5)
        pytest.fail("expected HTTPError for unmatched route")
    except urllib.error.HTTPError as exc:
        assert exc.code == 404
        body = json.loads(exc.read())
        assert body["error"] == "Not Found"
        assert body["requested"] == {"method": "GET", "path": "/unknown/endpoint"}
        assert len(body["available_routes"]) == 4


def test_cli_mock_405_diagnostic_with_allow_header(spawn_mock_server) -> None:
    """Test that a registered path with an unsupported method returns 405 + Allow header."""
    port = _free_port()
    spawn_mock_server([FIXTURE, "--port", str(port)])
    _wait_for_server("127.0.0.1", port)

    request = urllib.request.Request(f"http://127.0.0.1:{port}/pets", method="PATCH")
    try:
        urllib.request.urlopen(request, timeout=5)
        pytest.fail("expected HTTPError for unsupported method")
    except urllib.error.HTTPError as exc:
        assert exc.code == 405
        assert exc.headers.get("Allow") == "GET, POST"
        body = json.loads(exc.read())
        assert body["error"] == "Method Not Allowed"
        assert body["allowed_methods"] == ["GET", "POST"]


def test_cli_mock_missing_file_exits_1() -> None:
    """Test that a nonexistent test cases file exits 1 with a stderr diagnostic."""
    runner = CliRunner()
    result = runner.invoke(cli, ["mock", "tests/fixtures/does_not_exist.jsonl"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_cli_mock_empty_file_exits_1(tmp_path: Path) -> None:
    """Test that a file with no positive test cases exits 1 with a stderr diagnostic."""
    empty_file = tmp_path / "empty.jsonl"
    empty_file.write_text("", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(cli, ["mock", str(empty_file)])
    assert result.exit_code == 1
    assert "no valid positive test cases" in result.output.lower()


def test_cli_mock_port_conflict_exits_1() -> None:
    """Test that binding an already-occupied port exits 1 with a stderr diagnostic.

    A non-reuse-address listener occupies the port directly rather than another
    `specprobe mock` instance: on Windows, two sockets that both set SO_REUSEADDR
    (as MockServer does) are permitted to bind the same port simultaneously, which
    would make a same-process collision fail to reproduce the conflict.
    """
    occupier = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupier.bind(("127.0.0.1", 0))
    occupier.listen(1)
    occupied_port = occupier.getsockname()[1]
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "specprobe.cli", "mock", FIXTURE, "--port", str(occupied_port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _out, err = proc.communicate(timeout=10)
        assert proc.returncode == 1
        assert "Failed to bind port" in err
    finally:
        occupier.close()
