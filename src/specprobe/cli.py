"""Click CLI command group and entrypoint for SpecProbe."""

import json
import sys
import click
from specprobe.chunker.extractor import OperationExtractor
from specprobe.chunker.loader import SpecLoadError, load_openapi_spec
from specprobe.formatters.jsonl import stream_chunks_as_jsonl


@click.group()
@click.version_option(package_name="specprobe", prog_name="specprobe")
def cli() -> None:
    """SpecProbe: Developer CLI for probing, chunking, and testing API specifications."""


@cli.command("chunk")
@click.argument("spec_file", type=click.Path(allow_dash=True))
@click.option(
    "--schema-depth",
    type=int,
    default=2,
    show_default=True,
    help="Maximum traversal depth for referenced component schemas.",
)
@click.option(
    "--max-tokens",
    type=int,
    default=2000,
    show_default=True,
    help="Configurable token budget threshold for chunk size warnings.",
)
@click.option(
    "--op",
    "operation_id",
    type=str,
    default=None,
    help="Spot check a single operation chunk by operationId (explicit or synthesized).",
)
@click.option(
    "--stats",
    is_flag=True,
    default=False,
    help="Exclusive mode: display human-readable summary table of operation counts and sizes.",
)
def chunk_command(
    spec_file: str,
    schema_depth: int,
    max_tokens: int,
    operation_id: str | None,
    stats: bool,
) -> None:
    """Decompose an OpenAPI 3.0 or 3.1 specification into discrete per-operation chunks with pruned schemas."""
    try:
        raw_spec = load_openapi_spec(spec_file)
    except SpecLoadError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error: Unexpected failure reading specification: {exc}", err=True)
        sys.exit(1)

    extractor = OperationExtractor(raw_spec, schema_depth=schema_depth)
    chunks_iter = extractor.extract_operations()

    # If --op is specified, spot check a single operation
    if operation_id:
        for chunk in chunks_iter:
            if chunk.metadata.operationId == operation_id:
                click.echo(json.dumps(chunk.model_dump(), indent=2, ensure_ascii=False))
                return
        click.echo(f"Error: Operation '{operation_id}' not found.", err=True)
        sys.exit(1)

    # Stream chunks as JSONL
    for chunk_line in stream_chunks_as_jsonl(chunks_iter):
        click.echo(chunk_line, nl=False)


if __name__ == "__main__":
    cli()
