"""Orchestration engine and input parsing for test artifact exporters."""

import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from specprobe.exporter.http_client import generate_http_document
from specprobe.exporter.models import ExportConfig, ExportFormat
from specprobe.exporter.postman import generate_postman_collection
from specprobe.generator.models import GeneratedTestCase


def parse_test_cases(lines: Iterable[str]) -> list[GeneratedTestCase]:
    """Parse JSONL lines into a validated list of GeneratedTestCase records.

    Parameters
    ----------
    lines : Iterable[str]
        Iterable of raw lines from a file or standard input.

    Returns
    -------
    list[GeneratedTestCase]
        List of validated test cases. Empty list if input has no test cases.

    Raises
    ------
    ValueError
        If any line is invalid JSON or does not conform to GeneratedTestCase schema.
    """
    test_cases: list[GeneratedTestCase] = []

    for line_num, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        try:
            raw_data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Line {line_num}: invalid JSON: {exc}") from exc

        try:
            tc = GeneratedTestCase.model_validate(raw_data)
        except ValidationError as exc:
            raise ValueError(f"Line {line_num}: schema validation failed: {exc}") from exc

        test_cases.append(tc)

    return test_cases


def read_test_cases(source: str | Path | None = None) -> list[GeneratedTestCase]:
    """Read and validate test cases from a file path or standard input.

    Parameters
    ----------
    source : str | Path | None
        File path to read from, or None / '-' to read from sys.stdin.

    Returns
    -------
    list[GeneratedTestCase]
        Parsed and validated test cases.
    """
    if source is None or str(source).strip() == "-":
        lines = sys.stdin.readlines()
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: '{source}'")
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()

    return parse_test_cases(lines)


def export_batch(
    test_cases: list[GeneratedTestCase],
    config: ExportConfig,
    out_stream: Any = None,
    err_stream: Any = None,
) -> None:
    """Coordinate export of test cases to Postman, REST Client, or both.

    Parameters
    ----------
    test_cases : list[GeneratedTestCase]
        Test cases to export.
    config : ExportConfig
        Configuration options specifying format, output path, collection name, base URL.
    out_stream : Any | None
        Output stream for single-format stdout emission (defaults to sys.stdout).
    err_stream : Any | None
        Diagnostic stream for progress messages (defaults to sys.stderr).
    """
    if out_stream is None:
        out_stream = sys.stdout
    if err_stream is None:
        err_stream = sys.stderr

    if len(test_cases) == 0:
        err_stream.write("Notice: 0 test cases found.\n")

    if config.format == ExportFormat.POSTMAN:
        collection = generate_postman_collection(
            test_cases,
            collection_name=config.collection_name,
            base_url=config.base_url,
        )
        serialized = json.dumps(collection, indent=2, ensure_ascii=False) + "\n"

        if config.output_path:
            config.output_path.parent.mkdir(parents=True, exist_ok=True)
            config.output_path.write_text(serialized, encoding="utf-8", newline="\n")
            err_stream.write(
                f"Exported {len(test_cases)} test case(s) to "
                f"Postman collection at {config.output_path}\n"
            )
        else:
            out_stream.write(serialized)
            if hasattr(out_stream, "flush"):
                out_stream.flush()
    elif config.format == ExportFormat.HTTP:
        http_content = generate_http_document(
            test_cases,
            base_url=config.base_url,
        )
        if config.output_path:
            config.output_path.parent.mkdir(parents=True, exist_ok=True)
            config.output_path.write_text(http_content, encoding="utf-8", newline="\n")
            err_stream.write(
                f"Exported {len(test_cases)} test case(s) to "
                f"REST Client file at {config.output_path}\n"
            )
        else:
            out_stream.write(http_content)
            if hasattr(out_stream, "flush"):
                out_stream.flush()
    elif config.format == ExportFormat.BOTH:
        if config.output_path is None:
            raise ValueError("Output directory is required for dual-format export.")

        output_dir = config.output_path
        output_dir.mkdir(parents=True, exist_ok=True)

        collection = generate_postman_collection(
            test_cases,
            collection_name=config.collection_name,
            base_url=config.base_url,
        )
        postman_json = json.dumps(collection, indent=2, ensure_ascii=False) + "\n"
        col_file = output_dir / "collection.json"
        col_file.write_text(postman_json, encoding="utf-8", newline="\n")

        http_content = generate_http_document(
            test_cases,
            base_url=config.base_url,
        )
        http_file = output_dir / "requests.http"
        http_file.write_text(http_content, encoding="utf-8", newline="\n")

        count = len(test_cases)
        case_word = "test case" if count == 1 else "test cases"
        err_stream.write(f"Exported {count} {case_word} to {col_file} and {http_file}\n")
    else:
        raise ValueError(f"Unknown export format: '{config.format}'")
