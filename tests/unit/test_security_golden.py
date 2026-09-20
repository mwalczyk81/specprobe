"""Golden-file regression tests for security scheme export (T023).

Enforces Constitution Principle II (Deterministic Artifact Generation, Zero-LLM)
and Principle VI (Golden-file regression testing):
Verifies that generated Postman Collection v2.1.0 JSON and VS Code REST Client (.http)
artifacts with security-scheme-aware authentication match committed golden reference files
byte-for-byte without drift.
"""

from pathlib import Path

from click.testing import CliRunner

from specprobe.cli import cli

GOLDEN_DIR = Path("tests/fixtures/golden/security")
POSTMAN_GOLDEN = GOLDEN_DIR / "security.postman.json"
HTTP_GOLDEN = GOLDEN_DIR / "security.requests.http"
INPUT_FIXTURE = GOLDEN_DIR / "security_cases.jsonl"


def test_golden_security_postman_collection_byte_identical(tmp_path: Path) -> None:
    """Verify generated security Postman collection is 100% byte-identical to golden fixture."""
    runner = CliRunner()
    out_file = tmp_path / "collection.json"

    result = runner.invoke(
        cli,
        [
            "export",
            str(INPUT_FIXTURE),
            "--format",
            "postman",
            "-o",
            str(out_file),
            "--collection-name",
            "Security Schemes Test API Collection",
            "--base-url",
            "http://localhost:8000",
        ],
    )

    assert result.exit_code == 0, f"Export failed: {result.output}"
    assert out_file.exists(), "Exported collection file was not created"
    assert POSTMAN_GOLDEN.exists(), f"Golden reference file missing at {POSTMAN_GOLDEN}"

    actual_bytes = out_file.read_bytes()
    golden_bytes = POSTMAN_GOLDEN.read_bytes()

    assert actual_bytes == golden_bytes, (
        "Security Postman collection output diverged from golden reference fixture!"
    )


def test_golden_security_rest_client_http_byte_identical(tmp_path: Path) -> None:
    """Verify generated security REST Client document is 100% byte-identical to golden fixture."""
    runner = CliRunner()
    out_file = tmp_path / "requests.http"

    result = runner.invoke(
        cli,
        [
            "export",
            str(INPUT_FIXTURE),
            "--format",
            "http",
            "-o",
            str(out_file),
            "--base-url",
            "http://localhost:8000",
        ],
    )

    assert result.exit_code == 0, f"Export failed: {result.output}"
    assert out_file.exists(), "Exported .http file was not created"
    assert HTTP_GOLDEN.exists(), f"Golden reference file missing at {HTTP_GOLDEN}"

    actual_bytes = out_file.read_bytes()
    golden_bytes = HTTP_GOLDEN.read_bytes()

    assert actual_bytes == golden_bytes, (
        "Security REST Client .http output diverged from golden reference fixture!"
    )


def test_golden_security_dual_export_directory_byte_identical(tmp_path: Path) -> None:
    """Verify dual export (--format both) writes byte-identical security artifacts."""
    runner = CliRunner()
    out_dir = tmp_path / "exported_golden_security"

    result = runner.invoke(
        cli,
        [
            "export",
            str(INPUT_FIXTURE),
            "--format",
            "both",
            "-o",
            str(out_dir),
            "--collection-name",
            "Security Schemes Test API Collection",
            "--base-url",
            "http://localhost:8000",
        ],
    )

    assert result.exit_code == 0, f"Dual export failed: {result.output}"
    actual_col = (out_dir / "collection.json").read_bytes()
    actual_http = (out_dir / "requests.http").read_bytes()

    assert actual_col == POSTMAN_GOLDEN.read_bytes(), (
        "Dual-exported security Postman collection diverged from golden reference fixture!"
    )
    assert actual_http == HTTP_GOLDEN.read_bytes(), (
        "Dual-exported security REST Client document diverged from golden reference fixture!"
    )
