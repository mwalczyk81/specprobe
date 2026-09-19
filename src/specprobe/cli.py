"""Click CLI command group and entrypoint for SpecProbe."""

import json
import os
import sys
from pathlib import Path

import click

from specprobe.chunker.extractor import OperationExtractor
from specprobe.chunker.loader import SpecLoadError, load_openapi_spec
from specprobe.formatters.jsonl import stream_chunks_as_jsonl
from specprobe.index.store import QdrantIndexStore, index_chunk_stream


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
    """Decompose an OpenAPI 3.0 or 3.1 specification into discrete per-operation chunks
    with pruned schemas.
    """
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


@cli.command("index")
@click.argument("chunk_file", required=False, type=str)
@click.option(
    "--index-dir",
    type=click.Path(),
    default=lambda: os.environ.get("SPECPROBE_INDEX_DIR", ".specprobe/index"),
    show_default=True,
    help="Directory where Qdrant on-disk vector files are stored.",
)
@click.option(
    "--stats",
    is_flag=True,
    default=False,
    help="Exclusive mode: display collection size, unique specification chunk counts, and health.",
)
def index_command(
    chunk_file: str | None,
    index_dir: str,
    stats: bool,
) -> None:
    """Ingest JSONL operation chunks and update the persistent local vector index."""
    if stats:
        try:
            with QdrantIndexStore(index_path=index_dir) as store:
                report = store.get_stats()
        except Exception as exc:
            click.echo(f"Error: Failed to read index statistics: {exc}", err=True)
            sys.exit(1)

        click.echo("SpecProbe Vector Index Statistics:")
        click.echo(f"  Location: {report.index_path}")
        click.echo(f"  Status: {report.status}")
        click.echo(f"  Total Indexed Operations: {report.total_operations}")
        click.echo(f"  Unique Specifications: {report.unique_specifications}")
        for spec in report.specifications:
            click.echo(
                f"  * {spec.source_title} ({spec.source_version}): {spec.chunk_count} operations"
            )
        click.echo("Vector Configurations:")
        click.echo(f"  * dense: {report.vector_dimensions.get('dense')}")
        click.echo(f"  * sparse: {report.vector_dimensions.get('sparse')}")
        return

    # Ingestion mode
    if chunk_file and chunk_file != "-":
        path = Path(chunk_file)
        if not path.exists():
            click.echo(f"Error: Chunk file '{chunk_file}' not found.", err=True)
            sys.exit(1)
        try:
            try:
                with open(path, encoding="utf-8-sig") as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                with open(path, encoding="utf-16") as f:
                    lines = f.readlines()
        except Exception as exc:
            click.echo(f"Error: Could not read chunk file '{chunk_file}': {exc}", err=True)
            sys.exit(1)
    else:
        if chunk_file is None and sys.stdin.isatty():
            click.echo(
                "Error: Missing input chunk file or piped JSONL stream. "
                "Provide a chunk file or stream via stdin.",
                err=True,
            )
            sys.exit(1)
        lines = sys.stdin.readlines()

    try:
        count, specs, gen_id = index_chunk_stream(lines, index_path=index_dir)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error: Indexing failed: {exc}", err=True)
        sys.exit(1)

    if count == 0:
        click.echo("Empty input stream: 0 operations indexed.")
        return

    specs_str = ", ".join(f"'{title} {ver}'" for title, ver in specs)
    click.echo(
        f"Indexed {count} operations from {specs_str} into {index_dir} (generation: {gen_id[:8]})"
    )


@cli.command("search")
@click.argument("query", required=True, type=str)
@click.option(
    "--mode",
    type=click.Choice(["dense", "hybrid", "hybrid-rerank"], case_sensitive=False),
    default="hybrid",
    show_default=True,
    help=(
        "Retrieval mode algorithm: 'dense' (cosine vector similarity), "
        "'hybrid' (dense + sparse BM25 with reciprocal rank fusion), or "
        "'hybrid-rerank' (hybrid retrieval followed by local cross-encoder reranking). "
        "NOTE: The 'score' field is an ordinal metric valid only within a single search call. "
        "Scores are not comparable across --mode values or separate queries."
    ),
)
@click.option(
    "-n",
    "--limit",
    type=int,
    default=5,
    show_default=True,
    help="Maximum number of top matching operations to return.",
)
@click.option(
    "--tag",
    type=str,
    default=None,
    help="Filter matches to operations containing this tag.",
)
@click.option(
    "--method",
    type=str,
    default=None,
    help="Filter matches to operations with this HTTP method (e.g. GET, POST).",
)
@click.option(
    "--deprecated/--no-deprecated",
    default=None,
    help="Filter matches by deprecation status.",
)
@click.option(
    "--source-title",
    type=str,
    default=None,
    help="Filter matches to operations from this specification title.",
)
@click.option(
    "--source-version",
    type=str,
    default=None,
    help="Filter matches to operations from this specification version.",
)
@click.option(
    "--full",
    is_flag=True,
    default=False,
    help="Include complete OperationChunk payload under 'chunk' in each result object.",
)
@click.option(
    "--index-dir",
    type=click.Path(),
    default=lambda: os.environ.get("SPECPROBE_INDEX_DIR", ".specprobe/index"),
    show_default=True,
    help="Directory where Qdrant vector files are located.",
)
def search_command(
    query: str,
    mode: str,
    limit: int,
    tag: str | None,
    method: str | None,
    deprecated: bool | None,
    source_title: str | None,
    source_version: str | None,
    full: bool,
    index_dir: str,
) -> None:
    """Search indexed OpenAPI operations using natural language with optional filters.

    Results are formatted as a JSON array of SearchMatch objects. The 'score' field
    is an ordinal metric valid only within a single query invocation; scores are not
    calibrated probabilities and cannot be compared across different retrieval modes.
    """
    from specprobe.search.engine import SearchEngine, SearchMode

    index_path = Path(index_dir)
    if not index_path.exists():
        click.echo(
            f"Error: Index not found at '{index_dir}'. Run 'specprobe index' first.",
            err=True,
        )
        sys.exit(1)

    try:
        engine = SearchEngine(index_path=index_dir)
        matches = engine.search(
            query=query,
            mode=SearchMode(mode.lower()),
            limit=limit,
            tag=tag,
            method=method,
            deprecated=deprecated,
            source_title=source_title,
            source_version=source_version,
            full=full,
        )
    except Exception as exc:
        click.echo(f"Error: Search execution failed: {exc}", err=True)
        sys.exit(1)

    output = [m.model_dump(mode="json") for m in matches]
    click.echo(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    cli()
