"""Multi-threaded local HTTP mock server built on the standard library."""

import json
import signal
import threading
import time
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from rich.console import Console
from rich.table import Table

from specprobe.mock.models import MockAccessLogEntry, MockServerConfig
from specprobe.mock.router import (
    MockRouter,
    build_method_not_allowed_response,
    build_not_found_response,
)

__all__ = ["MockServer", "MockRequestHandler", "format_access_log_line"]


def _status_text(status_code: int) -> str:
    try:
        reason = HTTPStatus(status_code).phrase
    except ValueError:
        reason = ""
    return f"{status_code} {reason}".strip()


def format_access_log_line(entry: MockAccessLogEntry, raw_path: str) -> str:
    """Render a single-line access log entry: `[HH:MM:SS] METHOD /path -> STATUS (Nms)`."""
    timestamp = entry.timestamp.strftime("%H:%M:%S")
    status_text = _status_text(entry.status_code)
    line = f"[{timestamp}] {entry.method:<7}{raw_path} -> {status_text} ({entry.latency_ms:.1f}ms)"
    if not entry.matched:
        line += " [UNMATCHED]"
    return line


class MockRequestHandler(BaseHTTPRequestHandler):
    """Dispatches incoming HTTP requests against the owning MockServer's MockRouter."""

    server: "MockServer"

    def log_message(self, format: str, *args: object) -> None:
        # Suppress http.server's default stderr access log; MockServer emits its own.
        pass

    def _handle(self) -> None:
        start = time.perf_counter()
        raw_path = self.path
        match_path = urlsplit(raw_path).path
        method = self.command

        # Drain any request body off the wire even though matching ignores it:
        # leaving unread bytes in the socket when the handler closes the
        # connection can surface as a client-side connection reset.
        content_length = int(self.headers.get("Content-Length", 0) or 0)
        if content_length:
            self.rfile.read(content_length)

        route = self.server.router.match_route(method, match_path)
        if route is not None:
            status_code = route.response.status_code
            headers = dict(route.response.headers)
            body = route.response.body
            matched = True
        else:
            allowed = self.server.router.find_allowed_methods(match_path)
            if allowed:
                status_code = 405
                diagnostic = build_method_not_allowed_response(method, match_path, allowed)
                headers = {"Content-Type": "application/json", "Allow": ", ".join(allowed)}
            else:
                status_code = 404
                diagnostic = build_not_found_response(method, match_path, self.server.router.routes)
                headers = {"Content-Type": "application/json"}
            body = json.dumps(diagnostic).encode("utf-8")
            matched = False

        self.send_response(status_code)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body and method != "HEAD":
            self.wfile.write(body)

        latency_ms = (time.perf_counter() - start) * 1000
        entry = MockAccessLogEntry(
            timestamp=datetime.now(UTC),
            method=method,
            path=match_path,
            status_code=status_code,
            latency_ms=latency_ms,
            matched=matched,
        )
        self.server.log_access(entry, raw_path)

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_PATCH = _handle
    do_OPTIONS = _handle
    do_HEAD = _handle


class MockServer(ThreadingHTTPServer):
    """Multi-threaded mock HTTP server serving canned MockRoute responses."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        config: MockServerConfig,
        router: MockRouter,
        console: Console | None = None,
    ) -> None:
        self.config = config
        self.router = router
        self.console = console if console is not None else Console()
        super().__init__((config.host, config.port), MockRequestHandler)

    def log_access(self, entry: MockAccessLogEntry, raw_path: str) -> None:
        self.console.print(format_access_log_line(entry, raw_path))

    def print_startup_banner(self, source_label: str) -> None:
        routes = self.router.routes
        url = f"http://{self.config.host}:{self.server_port}"
        self.console.print("[bold]SpecProbe Mock Server[/bold]")
        self.console.print(f"Running at: {url}")
        self.console.print(f"Loaded: {len(routes)} positive route(s) from {source_label}")
        if routes:
            table = Table()
            table.add_column("Method")
            table.add_column("Path")
            table.add_column("Expected Status")
            table.add_column("Operation ID")
            for route in routes:
                table.add_row(
                    route.method,
                    route.path,
                    _status_text(route.response.status_code),
                    route.operation_id,
                )
            self.console.print(table)
        self.console.print("Press Ctrl+C to stop the server.")

    def serve_until_interrupted(self, poll_interval: float = 0.1) -> int:
        """Serve requests on a background thread until SIGINT/SIGTERM/Ctrl+C, then
        cleanly shut down and release the socket. Returns process exit code 0.
        """
        server_thread = threading.Thread(
            target=self.serve_forever, kwargs={"poll_interval": poll_interval}, daemon=True
        )
        server_thread.start()

        stop_event = threading.Event()

        def _handle_signal(signum: int, frame: object) -> None:
            stop_event.set()

        previous_sigint = signal.signal(signal.SIGINT, _handle_signal)
        previous_sigterm = None
        if hasattr(signal, "SIGTERM"):
            previous_sigterm = signal.signal(signal.SIGTERM, _handle_signal)

        try:
            while not stop_event.is_set():
                stop_event.wait(timeout=poll_interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.console.print("\nShutting down mock server...")
            self.shutdown()
            self.server_close()
            signal.signal(signal.SIGINT, previous_sigint)
            if previous_sigterm is not None:
                signal.signal(signal.SIGTERM, previous_sigterm)

        return 0
