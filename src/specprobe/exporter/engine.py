"""Orchestration engine and input parsing for test artifact exporters."""

import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from specprobe.exporter.http_client import (
    generate_http_document,
    generate_rest_client_environments,
)
from specprobe.exporter.models import ExportConfig, ExportEnvironment, ExportFormat
from specprobe.exporter.postman import (
    generate_postman_collection,
    generate_postman_environment,
)
from specprobe.exporter.utils import sanitize_environment_filename
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


def parse_env_cli_option(env_strs: Iterable[str]) -> list[ExportEnvironment]:
    """Parse repeatable CLI --env strings formatted as <name>=<url>.

    Parameters
    ----------
    env_strs : Iterable[str]
        Iterable of raw environment strings from the CLI.

    Returns
    -------
    list[ExportEnvironment]
        List of parsed and validated ExportEnvironment instances.

    Raises
    ------
    ValueError
        If an environment string is not in <name>=<url> format, or if duplicate
        environment names are supplied.
    """
    envs: list[ExportEnvironment] = []
    seen_names: set[str] = set()

    for item in env_strs:
        raw = item.strip()
        if "=" not in raw:
            raise ValueError(f"Invalid environment format '{item}'. Expected '<name>=<url>'.")
        name_part, url_part = raw.split("=", 1)
        name = name_part.strip()
        url = url_part.strip()
        if not name or not url:
            raise ValueError(f"Invalid environment format '{item}'. Expected '<name>=<url>'.")
        if name in seen_names:
            raise ValueError(f"Duplicate environment name '{name}' specified.")
        seen_names.add(name)
        envs.append(ExportEnvironment(name=name, base_url=url))

    return envs


def load_environment_config_file(file_path: Path | str) -> list[ExportEnvironment]:
    """Load environments from a JSON (.json) or YAML (.yaml, .yml) configuration file.

    Parameters
    ----------
    file_path : Path | str
        Path to the configuration file.

    Returns
    -------
    list[ExportEnvironment]
        List of parsed ExportEnvironment instances.

    Raises
    ------
    FileNotFoundError
        If the configuration file does not exist.
    ValueError
        If the file has an unsupported extension or contains invalid syntax/schema.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Environment configuration file not found: '{path}'")

    suffix = path.suffix.lower()
    if suffix not in (".json", ".yaml", ".yml"):
        raise ValueError(
            f"Unsupported environment file extension '{path.suffix}'. "
            "Expected .json, .yaml, or .yml."
        )

    content = path.read_text(encoding="utf-8")
    try:
        if suffix == ".json":
            raw_data = json.loads(content)
        else:
            raw_data = yaml.safe_load(content)
    except Exception as exc:
        raise ValueError(f"Failed to parse environment file '{path.name}': {exc}") from exc

    if not isinstance(raw_data, dict):
        raise ValueError(
            f"Invalid environment file structure in '{path.name}'. "
            "Expected top-level mapping of environment names."
        )

    envs: list[ExportEnvironment] = []
    for env_name, env_data in raw_data.items():
        if not isinstance(env_data, dict):
            raise ValueError(
                f"Environment '{env_name}' in '{path.name}' must be a dictionary of properties."
            )
        base_url = env_data.get("baseUrl") or env_data.get("base_url")
        if not base_url or not str(base_url).strip():
            raise ValueError(
                f"Environment '{env_name}' in '{path.name}' is missing required 'baseUrl' setting."
            )

        variables: dict[str, str] = {}
        for k, v in env_data.items():
            if k not in ("baseUrl", "base_url") and v is not None:
                variables[str(k)] = str(v)

        envs.append(
            ExportEnvironment(
                name=str(env_name).strip(),
                base_url=str(base_url).strip(),
                variables=variables,
            )
        )

    return envs


def merge_environments(
    file_envs: list[ExportEnvironment],
    cli_envs: list[ExportEnvironment],
) -> list[ExportEnvironment]:
    """Merge file-defined and CLI-defined environments.

    CLI environment definitions take precedence over file-defined environments
    with identical names.

    Parameters
    ----------
    file_envs : list[ExportEnvironment]
        Environments loaded from configuration file.
    cli_envs : list[ExportEnvironment]
        Environments passed directly via CLI flags.

    Returns
    -------
    list[ExportEnvironment]
        Combined list of environments.
    """
    env_map: dict[str, ExportEnvironment] = {e.name: e for e in file_envs}
    for e in cli_envs:
        env_map[e.name] = e
    return list(env_map.values())


def _resolve_output_paths(output_path: Path, default_filename: str) -> tuple[Path, Path]:
    """Resolve primary artifact file path and environment directory.

    If output_path is an existing directory or has no file suffix, treat it as a directory.
    Otherwise, treat output_path as the primary file path and its parent as the
    environment directory.
    """
    if output_path.is_dir() or (not output_path.exists() and output_path.suffix == ""):
        out_dir = output_path
        primary_file = out_dir / default_filename
    else:
        primary_file = output_path
        out_dir = output_path.parent
    return primary_file, out_dir


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

    has_environments = bool(config.environments)

    if config.format == ExportFormat.POSTMAN:
        include_variables = not has_environments
        collection = generate_postman_collection(
            test_cases,
            collection_name=config.collection_name,
            base_url=config.base_url,
            include_variables=include_variables,
        )
        serialized = json.dumps(collection, indent=2, ensure_ascii=False) + "\n"

        if config.output_path:
            primary_file, env_dir = _resolve_output_paths(config.output_path, "collection.json")
            primary_file.parent.mkdir(parents=True, exist_ok=True)
            primary_file.write_text(serialized, encoding="utf-8", newline="\n")

            if has_environments:
                env_dir.mkdir(parents=True, exist_ok=True)
                for env in config.environments:
                    safe_name = sanitize_environment_filename(env.name)
                    env_dict = generate_postman_environment(env, test_cases)
                    env_file = env_dir / f"{safe_name}.postman_environment.json"
                    env_file.write_text(
                        json.dumps(env_dict, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                        newline="\n",
                    )
                count = len(config.environments)
                file_word = "environment file" if count == 1 else "environment files"
                err_stream.write(
                    f"Exported {len(test_cases)} test case(s) to "
                    f"Postman collection at {primary_file} and {count} {file_word} to {env_dir}\n"
                )
            else:
                err_stream.write(
                    f"Exported {len(test_cases)} test case(s) to "
                    f"Postman collection at {primary_file}\n"
                )
        else:
            out_stream.write(serialized)
            if hasattr(out_stream, "flush"):
                out_stream.flush()
    elif config.format == ExportFormat.HTTP:
        include_env_header = not has_environments
        http_content = generate_http_document(
            test_cases,
            base_url=config.base_url,
            include_env_header=include_env_header,
        )

        if config.output_path:
            primary_file, env_dir = _resolve_output_paths(config.output_path, "requests.http")
            primary_file.parent.mkdir(parents=True, exist_ok=True)
            primary_file.write_text(http_content, encoding="utf-8", newline="\n")

            if has_environments:
                env_dir.mkdir(parents=True, exist_ok=True)
                env_dict = generate_rest_client_environments(config.environments, test_cases)
                env_file = env_dir / "http-client.env.json"
                env_file.write_text(
                    json.dumps(env_dict, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                err_stream.write(
                    f"Exported {len(test_cases)} test case(s) to "
                    f"REST Client file at {primary_file} and environments to {env_file}\n"
                )
            else:
                err_stream.write(
                    f"Exported {len(test_cases)} test case(s) to "
                    f"REST Client file at {primary_file}\n"
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

        include_vars = not has_environments
        collection = generate_postman_collection(
            test_cases,
            collection_name=config.collection_name,
            base_url=config.base_url,
            include_variables=include_vars,
        )
        postman_json = json.dumps(collection, indent=2, ensure_ascii=False) + "\n"
        col_file = output_dir / "collection.json"
        col_file.write_text(postman_json, encoding="utf-8", newline="\n")

        include_env_header = not has_environments
        http_content = generate_http_document(
            test_cases,
            base_url=config.base_url,
            include_env_header=include_env_header,
        )
        http_file = output_dir / "requests.http"
        http_file.write_text(http_content, encoding="utf-8", newline="\n")

        count = len(test_cases)
        case_word = "test case" if count == 1 else "test cases"

        if has_environments:
            # Emit Postman environment files
            for env in config.environments:
                safe_name = sanitize_environment_filename(env.name)
                env_dict = generate_postman_environment(env, test_cases)
                env_file = output_dir / f"{safe_name}.postman_environment.json"
                env_file.write_text(
                    json.dumps(env_dict, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )

            # Emit REST Client environment file
            rest_env_dict = generate_rest_client_environments(config.environments, test_cases)
            rest_env_file = output_dir / "http-client.env.json"
            rest_env_file.write_text(
                json.dumps(rest_env_dict, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )

            env_count = len(config.environments)
            env_word = "environment file" if env_count == 1 else "environment files"
            err_stream.write(
                f"Exported {count} {case_word} to {col_file}, {http_file}, "
                f"{env_count} Postman {env_word}, and {rest_env_file}\n"
            )
        else:
            err_stream.write(f"Exported {count} {case_word} to {col_file} and {http_file}\n")
    else:
        raise ValueError(f"Unknown export format: '{config.format}'")
