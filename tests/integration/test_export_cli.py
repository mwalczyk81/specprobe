"""Integration tests for specprobe export CLI command."""

import json
from pathlib import Path

from click.testing import CliRunner

from specprobe.cli import cli


def test_export_from_file_stdout(tmp_path: Path) -> None:
    """Verify export reads test cases from file and emits valid Postman collection to stdout."""
    runner = CliRunner()
    fixture_path = "tests/fixtures/generated_tests.jsonl"

    result = runner.invoke(cli, ["export", fixture_path, "--format", "postman"])

    assert result.exit_code == 0
    collection = json.loads(result.stdout)
    assert collection["info"]["schema"] == (
        "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    )
    assert collection["variable"][0]["key"] == "baseUrl"
    assert len(collection["item"]) == 2  # "pets" folder and untagged item


def test_export_from_stdin_pipe() -> None:
    """Verify export reads test cases from stdin pipe."""
    runner = CliRunner()
    fixture_path = Path("tests/fixtures/generated_tests.jsonl")
    content = fixture_path.read_text(encoding="utf-8")

    result = runner.invoke(cli, ["export", "--format", "postman"], input=content)

    assert result.exit_code == 0
    collection = json.loads(result.stdout)
    assert collection["info"]["schema"] == (
        "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    )
    assert len(collection["item"]) == 2


def test_export_to_output_file(tmp_path: Path) -> None:
    """Verify export writes collection to output file specified via -o/--output."""
    runner = CliRunner()
    fixture_path = "tests/fixtures/generated_tests.jsonl"
    out_file = tmp_path / "exported" / "my_collection.json"

    result = runner.invoke(
        cli,
        [
            "export",
            fixture_path,
            "--format",
            "postman",
            "-o",
            str(out_file),
            "--collection-name",
            "Custom Petstore Suite",
            "--base-url",
            "https://pets.example.com/api",
        ],
    )

    assert result.exit_code == 0
    assert out_file.exists()

    collection = json.loads(out_file.read_text(encoding="utf-8"))
    assert collection["info"]["name"] == "Custom Petstore Suite"
    assert collection["variable"][0]["value"] == "https://pets.example.com/api"


def test_export_missing_file() -> None:
    """Verify error reporting and exit code 1 when input file does not exist."""
    runner = CliRunner()
    result = runner.invoke(cli, ["export", "non_existent_file.jsonl", "--format", "postman"])

    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "not found" in (result.stderr or "").lower()


def test_export_malformed_jsonl(tmp_path: Path) -> None:
    """Verify line-numbered error reporting and exit code 1 on malformed JSONL."""
    runner = CliRunner()
    bad_file = tmp_path / "bad.jsonl"
    bad_file.write_text('{"operation_id": "valid"}\n{bad_json}\n', encoding="utf-8")

    result = runner.invoke(cli, ["export", str(bad_file), "--format", "postman"])

    assert result.exit_code == 1
    output_or_err = (result.output + (result.stderr or "")).lower()
    assert "line 1" in output_or_err or "line 2" in output_or_err


def test_export_empty_file_produces_empty_collection(tmp_path: Path) -> None:
    """Verify empty input produces a valid empty Postman collection and exits code 0."""
    runner = CliRunner()
    empty_file = tmp_path / "empty.jsonl"
    empty_file.write_text("", encoding="utf-8")

    result = runner.invoke(cli, ["export", str(empty_file), "--format", "postman"])

    assert result.exit_code == 0
    collection = json.loads(result.stdout)
    assert collection["item"] == []
    assert collection["info"]["schema"] == (
        "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    )
    assert "0 test cases found" in result.stderr


def test_export_http_from_file_stdout() -> None:
    """Verify export reads test cases from file and emits REST Client format to stdout."""
    runner = CliRunner()
    fixture_path = "tests/fixtures/generated_tests.jsonl"

    result = runner.invoke(cli, ["export", fixture_path, "--format", "http"])

    assert result.exit_code == 0
    assert result.stdout.startswith("@baseUrl = http://localhost:8000\n\n")
    assert "###\n# @name listPets\n# Operation: listPets" in result.stdout
    assert "GET {{baseUrl}}/pets?limit=10 HTTP/1.1" in result.stdout


def test_export_http_from_stdin_pipe() -> None:
    """Verify export reads test cases from stdin pipe and emits REST Client format."""
    runner = CliRunner()
    fixture_path = Path("tests/fixtures/generated_tests.jsonl")
    content = fixture_path.read_text(encoding="utf-8")

    result = runner.invoke(cli, ["export", "--format", "http"], input=content)

    assert result.exit_code == 0
    assert result.stdout.startswith("@baseUrl = http://localhost:8000\n\n")
    assert "###\n# @name createPets" in result.stdout
    assert "POST {{baseUrl}}/pets HTTP/1.1" in result.stdout


def test_export_http_to_output_file(tmp_path: Path) -> None:
    """Verify export writes REST Client document to output file specified via -o/--output."""
    runner = CliRunner()
    fixture_path = "tests/fixtures/generated_tests.jsonl"
    out_file = tmp_path / "exported" / "requests.http"

    result = runner.invoke(
        cli,
        [
            "export",
            fixture_path,
            "--format",
            "http",
            "-o",
            str(out_file),
            "--base-url",
            "https://pets.example.com/api",
        ],
    )

    assert result.exit_code == 0
    assert out_file.exists()

    content = out_file.read_text(encoding="utf-8")
    assert content.startswith("@baseUrl = https://pets.example.com/api\n\n")
    assert "###\n# @name showPetById" in content
    assert "Exported 4 test case(s) to REST Client file" in result.stderr


def test_export_http_empty_file_produces_empty_document(tmp_path: Path) -> None:
    """Verify empty input produces an empty .http file and exits code 0."""
    runner = CliRunner()
    empty_file = tmp_path / "empty.jsonl"
    empty_file.write_text("", encoding="utf-8")

    result = runner.invoke(cli, ["export", str(empty_file), "--format", "http"])

    assert result.exit_code == 0
    assert result.stdout == ""
    assert "0 test cases found" in result.stderr


def test_export_default_format_is_both_without_output_fails() -> None:
    """Verify default format is 'both' and fails with exit code 1 when --output is omitted."""
    runner = CliRunner()
    fixture_path = "tests/fixtures/generated_tests.jsonl"

    result = runner.invoke(cli, ["export", fixture_path])

    assert result.exit_code == 1
    assert (
        "option '--output <directory>' is required"
        in (result.output + (result.stderr or "")).lower()
    )


def test_export_both_without_output_fails_early_before_stdin() -> None:
    """Verify --format both fails immediately when --output is omitted without reading stdin."""
    runner = CliRunner()
    # Pass arbitrary piped content; it should exit with code 1 before reading
    result = runner.invoke(cli, ["export", "--format", "both"], input="some piped content")

    assert result.exit_code == 1
    assert (
        "option '--output <directory>' is required"
        in (result.output + (result.stderr or "")).lower()
    )


def test_export_both_to_directory(tmp_path: Path) -> None:
    """Verify dual export writes both collection.json and requests.http to directory."""
    runner = CliRunner()
    fixture_path = "tests/fixtures/generated_tests.jsonl"
    out_dir = tmp_path / "exported_dual"

    result = runner.invoke(
        cli,
        [
            "export",
            fixture_path,
            "--format",
            "both",
            "-o",
            str(out_dir),
            "--collection-name",
            "Dual Petstore Suite",
            "--base-url",
            "https://api.petstore.io",
        ],
    )

    assert result.exit_code == 0
    assert out_dir.exists()

    col_file = out_dir / "collection.json"
    http_file = out_dir / "requests.http"
    assert col_file.exists()
    assert http_file.exists()

    collection = json.loads(col_file.read_text(encoding="utf-8"))
    assert collection["info"]["name"] == "Dual Petstore Suite"
    assert collection["variable"][0]["value"] == "https://api.petstore.io"
    assert len(collection["item"]) == 2

    http_content = http_file.read_text(encoding="utf-8")
    assert http_content.startswith("@baseUrl = https://api.petstore.io\n\n")
    assert "###\n# @name listPets" in http_content

    # Verify exact stderr message per contracts/cli-export.md
    expected_msg = f"Exported 4 test cases to {col_file} and {http_file}"
    assert expected_msg in result.stderr


def test_export_both_directory_auto_created(tmp_path: Path) -> None:
    """Verify nested parent directories are automatically created when exporting both."""
    runner = CliRunner()
    fixture_path = "tests/fixtures/generated_tests.jsonl"
    nested_dir = tmp_path / "deep" / "nested" / "output_dir"
    assert not nested_dir.exists()

    result = runner.invoke(
        cli,
        ["export", fixture_path, "--format", "both", "-o", str(nested_dir)],
    )

    assert result.exit_code == 0
    assert (nested_dir / "collection.json").exists()
    assert (nested_dir / "requests.http").exists()


def test_export_both_empty_input(tmp_path: Path) -> None:
    """Verify empty input with --format both creates valid empty collection and empty .http file."""
    runner = CliRunner()
    empty_file = tmp_path / "empty.jsonl"
    empty_file.write_text("", encoding="utf-8")
    out_dir = tmp_path / "empty_out"

    result = runner.invoke(
        cli,
        ["export", str(empty_file), "--format", "both", "-o", str(out_dir)],
    )

    assert result.exit_code == 0
    col_file = out_dir / "collection.json"
    http_file = out_dir / "requests.http"

    assert col_file.exists()
    assert http_file.exists()

    col_data = json.loads(col_file.read_text(encoding="utf-8"))
    assert col_data["item"] == []
    assert http_file.read_text(encoding="utf-8") == ""

    assert "0 test cases found" in result.stderr
    assert f"Exported 0 test cases to {col_file} and {http_file}" in result.stderr


def test_export_both_single_test_case_singular_grammar(tmp_path: Path) -> None:
    """Verify singular 'test case' is used when exporting exactly 1 test case."""
    runner = CliRunner()
    single_file = tmp_path / "single.jsonl"
    fixture_path = Path("tests/fixtures/generated_tests.jsonl")
    # Take first line from fixture
    first_line = fixture_path.read_text(encoding="utf-8").strip().splitlines()[0]
    single_file.write_text(first_line + "\n", encoding="utf-8")
    out_dir = tmp_path / "single_out"

    result = runner.invoke(
        cli,
        ["export", str(single_file), "--format", "both", "-o", str(out_dir)],
    )

    assert result.exit_code == 0
    col_file = out_dir / "collection.json"
    http_file = out_dir / "requests.http"
    expected_msg = f"Exported 1 test case to {col_file} and {http_file}"
    assert expected_msg in result.stderr


def test_export_http_ignores_collection_name(tmp_path: Path) -> None:
    """Verify --collection-name is silently ignored when format is http."""
    runner = CliRunner()
    fixture_path = "tests/fixtures/generated_tests.jsonl"
    out_file = tmp_path / "test.http"

    result = runner.invoke(
        cli,
        [
            "export",
            fixture_path,
            "--format",
            "http",
            "-o",
            str(out_file),
            "--collection-name",
            "ShouldBeIgnored",
        ],
    )

    assert result.exit_code == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "ShouldBeIgnored" not in content
