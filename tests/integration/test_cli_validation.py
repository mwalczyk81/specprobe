"""Integration tests for specification validation and unsupported reference guardrails (US4)."""

import json
from pathlib import Path

from click.testing import CliRunner

from specprobe.cli import cli


def test_cli_swagger_20_rejection(swagger_20_path: Path) -> None:
    """Verify Swagger 2.0 specs are rejected with exit code 1 and descriptive error message."""
    runner = CliRunner()
    result = runner.invoke(cli, ["chunk", str(swagger_20_path)])

    assert result.exit_code == 1
    assert "Swagger 2.0 is not supported" in result.output
    assert "SpecProbe requires OpenAPI 3.0 or 3.1" in result.output


def test_cli_external_ref_warning(external_ref_spec_path: Path) -> None:
    """Verify external file references emit non-fatal warnings to stderr and metadata,
    with exit code 0.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["chunk", str(external_ref_spec_path)])

    assert result.exit_code == 0, f"Command failed: {result.output}"

    # Verify JSONL output on stdout has preserved raw $ref and metadata warning
    chunk = json.loads(result.stdout.strip())
    assert chunk["metadata"]["operationId"] == "getExternal"
    assert "LocalData" in chunk["components"]["schemas"]

    # Raw $ref string preserved in the operation chunk
    resp_500_ref = chunk["operation"]["responses"]["500"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    assert resp_500_ref == "common_models.yaml#/components/schemas/ExternalError"

    # Warning attached to chunk metadata
    warnings = chunk["metadata"]["warnings"]
    assert len(warnings) == 1
    expected_warning = (
        "External reference 'common_models.yaml#/components/schemas/ExternalError' "
        "is unsupported and was preserved without expansion."
    )
    assert expected_warning in warnings[0]

    # Advisory warning printed to stderr
    assert f"Warning: {expected_warning}" in result.stderr


def test_cli_external_ref_with_op(external_ref_spec_path: Path) -> None:
    """Verify --op spot check also preserves raw $ref and emits stderr warning for
    external references.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["chunk", str(external_ref_spec_path), "--op", "getExternal"])

    assert result.exit_code == 0, f"Command failed: {result.output}"

    chunk = json.loads(result.stdout.strip())
    assert chunk["metadata"]["operationId"] == "getExternal"
    expected_warning = (
        "External reference 'common_models.yaml#/components/schemas/ExternalError' "
        "is unsupported and was preserved without expansion."
    )
    assert expected_warning in chunk["metadata"]["warnings"]
    assert f"Warning: {expected_warning}" in result.stderr
