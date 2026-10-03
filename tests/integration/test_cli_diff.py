"""Integration tests for specprobe diff CLI command."""

import json
from pathlib import Path

from click.testing import CliRunner

from specprobe.cli import cli


def test_cli_diff_operations_exit_code_1_on_removed_op(tmp_path: Path) -> None:
    """Verify specprobe diff reports added and removed operations and exits 1 on removed op."""
    v1_file = tmp_path / "v1.yaml"
    v1_file.write_text(
        """openapi: 3.0.3
info:
  title: Pet API
  version: 1.0.0
paths:
  /pets:
    get:
      summary: List pets
      responses:
        '200':
          description: OK
  /pets/{id}:
    delete:
      summary: Delete pet
      responses:
        '204':
          description: No Content
""",
        encoding="utf-8",
    )

    v2_file = tmp_path / "v2.yaml"
    v2_file.write_text(
        """openapi: 3.0.3
info:
  title: Pet API
  version: 2.0.0
paths:
  /pets:
    get:
      summary: List pets
      responses:
        '200':
          description: OK
    post:
      summary: Create pet
      responses:
        '201':
          description: Created
""",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["diff", str(v1_file), str(v2_file)])

    assert result.exit_code == 1
    lines = [line.strip() for line in result.output.strip().split("\n") if line.strip()]
    assert len(lines) == 2

    records = [json.loads(line) for line in lines]
    types = {r["change_type"] for r in records}
    assert "operation_removed" in types
    assert "operation_added" in types


def test_cli_diff_exit_code_0_on_clean_or_addition_only(tmp_path: Path) -> None:
    """Verify specprobe diff exits with code 0 when only non-breaking additions exist."""
    v1_file = tmp_path / "v1.yaml"
    v1_file.write_text(
        """openapi: 3.0.3
info:
  title: Pet API
  version: 1.0.0
paths:
  /pets:
    get:
      summary: List pets
      responses:
        '200':
          description: OK
""",
        encoding="utf-8",
    )

    v2_file = tmp_path / "v2.yaml"
    v2_file.write_text(
        """openapi: 3.0.3
info:
  title: Pet API
  version: 2.0.0
paths:
  /pets:
    get:
      summary: List pets
      responses:
        '200':
          description: OK
    post:
      summary: Create pet
      responses:
        '201':
          description: Created
""",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["diff", str(v1_file), str(v2_file)])

    assert result.exit_code == 0
    lines = [line.strip() for line in result.output.strip().split("\n") if line.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["change_type"] == "operation_added"
    assert record["breaking"] is False


def test_cli_diff_file_not_found_exit_code_2() -> None:
    """Verify specprobe diff exits 2 and outputs error on stderr when input file is missing."""
    runner = CliRunner()
    result = runner.invoke(cli, ["diff", "nonexistent_v1.yaml", "nonexistent_v2.yaml"])
    assert result.exit_code == 2
    assert "Error:" in result.output or "Error:" in result.stderr


def test_cli_diff_invalid_syntax_exit_code_2(tmp_path: Path) -> None:
    """Verify specprobe diff exits 2 when an input file contains invalid syntax."""
    corrupt_file = tmp_path / "corrupt.yaml"
    corrupt_file.write_text("invalid: [unclosed yaml mapping", encoding="utf-8")
    valid_file = tmp_path / "valid.yaml"
    valid_file.write_text(
        """openapi: 3.0.3
info:
  title: Test API
  version: 1.0.0
paths: {}
""",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["diff", str(corrupt_file), str(valid_file)])
    assert result.exit_code == 2
    assert "Error:" in result.output or "Error:" in result.stderr


def test_cli_diff_summary_flag_and_schema_breaking(tmp_path: Path) -> None:
    """Verify --summary prints formatted table to stderr while stdout remains pure JSONL."""
    v1_file = tmp_path / "v1.yaml"
    v1_file.write_text(
        """openapi: 3.0.3
info:
  title: Store API
  version: 1.0.0
paths:
  /items:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name]
              properties:
                name: {type: string}
                price: {type: number}
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: object
                properties:
                  id: {type: string}
                  category: {type: string}
""",
        encoding="utf-8",
    )

    v2_file = tmp_path / "v2.yaml"
    v2_file.write_text(
        """openapi: 3.0.3
info:
  title: Store API
  version: 2.0.0
paths:
  /items:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name, price]
              properties:
                name: {type: string}
                price: {type: integer}
      responses:
        '201':
          description: Created
          content:
            application/json:
              schema:
                type: object
                properties:
                  id: {type: string}
""",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["diff", str(v1_file), str(v2_file), "--summary"])

    assert result.exit_code == 1
    # Check that summary table was printed to stderr
    assert "SpecProbe Specification Diff Summary" in result.stderr
    assert "Breaking Changes" in result.stderr

    # Verify stdout contains ONLY valid JSONL records
    stdout_lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    assert len(stdout_lines) > 0
    for line in stdout_lines:
        record = json.loads(line)
        assert record["breaking"] is True
