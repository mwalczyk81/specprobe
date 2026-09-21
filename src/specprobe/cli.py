"""Click CLI command group and entrypoint for SpecProbe."""

import json
import os
import statistics
import sys
import warnings
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from specprobe.audit.engine import (
    AuditEngine,
    load_artifact_items,
    load_spec_chunks,
)
from specprobe.chunker.extractor import OperationExtractor
from specprobe.chunker.loader import SpecLoadError, load_openapi_spec
from specprobe.chunker.models import ChunkingStats
from specprobe.exporter.engine import export_batch, read_test_cases
from specprobe.exporter.models import ExportConfig, ExportFormat
from specprobe.formatters.jsonl import stream_chunks_as_jsonl
from specprobe.generator.gateway import LLMGateway
from specprobe.index.store import QdrantIndexStore, index_chunk_stream

# Disable Hugging Face and tqdm progress bars so CLI stdout/stderr streams remain pure JSON
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TQDM_DISABLE", "1")
warnings.filterwarnings("ignore", message=".*Cannot enable progress bars.*")


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

    # If --stats is specified, display summary table of operation counts and sizes
    if stats:
        chunks = list(chunks_iter)
        token_counts = [chunk.metadata.estimated_tokens for chunk in chunks]
        all_warnings: list[str] = []
        oversized = 0
        for chunk in chunks:
            for w in chunk.metadata.warnings:
                if w not in all_warnings:
                    all_warnings.append(w)
            if chunk.metadata.estimated_tokens > max_tokens:
                oversized += 1

        total_ops = len(chunks)
        if total_ops > 0:
            min_tok = min(token_counts)
            max_tok = max(token_counts)
            median_tok = float(statistics.median(token_counts))
            avg_tok = float(statistics.mean(token_counts))
        else:
            min_tok = 0
            max_tok = 0
            median_tok = 0.0
            avg_tok = 0.0

        chunk_stats = ChunkingStats(
            total_operations=total_ops,
            min_tokens=min_tok,
            max_tokens=max_tok,
            median_tokens=median_tok,
            avg_tokens=avg_tok,
            oversized_chunks=oversized,
            warnings=all_warnings,
        )

        console = Console()
        table = Table(title="SpecProbe Chunking Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Total Operations", str(chunk_stats.total_operations))
        table.add_row("Min Tokens", str(chunk_stats.min_tokens))
        table.add_row("Max Tokens", str(chunk_stats.max_tokens))
        table.add_row("Median Tokens", f"{chunk_stats.median_tokens:.1f}")
        table.add_row("Avg Tokens", f"{chunk_stats.avg_tokens:.1f}")
        table.add_row("Oversized Chunks", str(chunk_stats.oversized_chunks))
        table.add_row("Warnings", str(len(chunk_stats.warnings)))
        console.print(table)
        return

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

        console = Console()
        console.print("SpecProbe Vector Index Statistics:")
        console.print(f"  Location: {report.index_path}")
        console.print(f"  Status: {report.status}")
        console.print(f"  Total Indexed Operations: {report.total_operations}")
        console.print(f"  Unique Specifications: {report.unique_specifications}")

        table = Table(title="Specifications")
        table.add_column("Spec Title", style="cyan")
        table.add_column("Version", style="magenta")
        table.add_column("Operation Count", justify="right", style="green")
        for spec in report.specifications:
            table.add_row(spec.source_title, spec.source_version, str(spec.chunk_count))
        console.print(table)

        console.print("Vector Configurations:")
        console.print(f"  * dense: {report.vector_dimensions.get('dense')}")
        console.print(f"  * sparse: {report.vector_dimensions.get('sparse')}")
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
@click.argument("query", required=False, default=None, type=str)
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
    query: str | None,
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

    clean_query = query.strip() if query is not None else None
    if not clean_query:
        has_filter = any(
            x is not None for x in [tag, method, deprecated, source_title, source_version]
        )
        if not has_filter:
            click.echo(
                "Error: Either a search query or at least one filter "
                "(--tag, --method, --deprecated, --source-title, --source-version) "
                "must be provided.",
                err=True,
            )
            sys.exit(1)

    index_path = Path(index_dir)
    if not index_path.exists():
        click.echo(
            f"Error: Index not found at '{index_dir}'. Run 'specprobe index' first.",
            err=True,
        )
        sys.exit(1)

    try:
        engine = SearchEngine(index_path=index_dir)
        if not clean_query:
            ctx = click.get_current_context()
            effective_limit = (
                limit
                if ctx.get_parameter_source("limit") != click.core.ParameterSource.DEFAULT
                else None
            )
            matches = engine.search_unranked(
                limit=effective_limit,
                tag=tag,
                method=method,
                deprecated=deprecated,
                source_title=source_title,
                source_version=source_version,
                full=full,
            )
        else:
            matches = engine.search(
                query=clean_query,
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


@cli.command("generate")
@click.argument("results_file", required=False, type=click.Path(dir_okay=False, allow_dash=True))
@click.option(
    "--model",
    type=str,
    default=lambda: os.environ.get("SPECPROBE_LLM_MODEL", "openai/local-model"),
    show_default=True,
    help="Model identifier string passed to LiteLLM.",
)
@click.option(
    "--api-base",
    type=str,
    default=None,
    show_default=False,
    help=(
        "Base endpoint URL for model requests "
        "(defaults to http://localhost:1234/v1 for local models; omitted for Bedrock)."
    ),
)
@click.option(
    "--temperature",
    type=float,
    default=lambda: float(os.environ.get("SPECPROBE_LLM_TEMPERATURE", "0.0")),
    show_default=True,
    help="Sampling temperature for LLM completions.",
)
@click.option(
    "--cache-dir",
    type=click.Path(),
    default=lambda: os.environ.get("SPECPROBE_CACHE_DIR", ".specprobe/cache"),
    show_default=True,
    help="Directory where LLM call cache files are stored.",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=lambda: os.environ.get("SPECPROBE_NO_CACHE", "false").lower() in ("true", "1", "yes"),
    show_default=True,
    help="Bypass existing disk cache entries and refresh cache records.",
)
@click.option(
    "--negative-auth/--no-negative-auth",
    default=True,
    show_default=True,
    help=(
        "Generate 401 (missing credentials) and 403 (invalid credentials) "
        "negative test cases for secured operations."
    ),
)
@click.option(
    "--not-found/--no-not-found",
    default=True,
    show_default=True,
    help=(
        "Generate 404 (resource not found) negative test cases for path-parameterized operations."
    ),
)
@click.option(
    "--invalid-input/--no-invalid-input",
    default=True,
    show_default=True,
    help=(
        "Generate 400 (invalid input) negative test cases for schema-constrained request bodies."
    ),
)
def generate_command(
    results_file: str | None,
    model: str,
    api_base: str | None,
    temperature: float,
    cache_dir: str,
    no_cache: bool,
    negative_auth: bool,
    not_found: bool,
    invalid_input: bool,
) -> None:
    """Generate schema-validated test cases from OpenAPI operation search results.

    Accepts search results JSON (emitted by 'specprobe search --full') via a file argument
    or standard input (stdin), invoking a local-first LLM gateway, and streaming
    validated GeneratedTestCase objects as JSON Lines (JSONL) to stdout.
    """
    from specprobe.generator.cache import DiskCache
    from specprobe.generator.engine import GenerationEngine, parse_search_results
    from specprobe.generator.gateway import LLMGateway

    # Read input from results_file or stdin
    raw_input = ""
    if results_file and results_file != "-":
        file_path = Path(results_file)
        if not file_path.exists():
            click.echo(f"Error: Results file not found at '{results_file}'.", err=True)
            sys.exit(1)
        try:
            raw_input = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            click.echo(f"Error reading file '{results_file}': {exc}", err=True)
            sys.exit(1)
    else:
        if sys.stdin.isatty():
            click.echo(
                "Error: No search results provided. Pass a file argument or pipe JSON via stdin.",
                err=True,
            )
            sys.exit(1)
        try:
            raw_input = sys.stdin.read()
        except Exception as exc:
            click.echo(f"Error reading stdin: {exc}", err=True)
            sys.exit(1)

    if not raw_input or not raw_input.strip():
        click.echo(
            "Error: No search results provided. Pass a file argument or pipe JSON via stdin.",
            err=True,
        )
        sys.exit(1)

    # Parse search results into OperationChunk list
    try:
        chunks = parse_search_results(raw_input)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if not chunks:
        # Empty array input produces 0 test cases and exits successfully
        sys.exit(0)

    # Initialize gateway with resolved options
    try:
        gateway = LLMGateway(
            model=model,
            api_base=api_base,
            temperature=temperature,
        )
    except Exception as exc:
        click.echo(f"Error: Gateway initialization failed: {exc}", err=True)
        sys.exit(1)

    cache = DiskCache(cache_dir=cache_dir, no_cache=no_cache)
    engine = GenerationEngine(gateway=gateway, cache=cache)
    batch_result = engine.generate_batch(
        chunks,
        stream_stdout=True,
        negative_auth=negative_auth,
        not_found=not_found,
        invalid_input=invalid_input,
    )

    if batch_result.total > 0 and batch_result.succeeded == 0:
        click.echo(
            f"Error: All {batch_result.total} operation(s) failed test generation.",
            err=True,
        )
        sys.exit(1)

    sys.exit(0)


@cli.command("export")
@click.argument(
    "test_cases_file",
    required=False,
    type=click.Path(dir_okay=False, allow_dash=True, path_type=Path),
)
@click.option(
    "--format",
    type=click.Choice(["postman", "http", "both"], case_sensitive=False),
    default="both",
    show_default=True,
    help="Target artifact format(s) to generate.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Destination output file path (for single format) or directory (for both).",
)
@click.option(
    "--collection-name",
    type=str,
    default=None,
    help="Title/name for Postman collection.",
)
@click.option(
    "--base-url",
    type=str,
    default="http://localhost:8000",
    show_default=True,
    help="Base URL for target API environment embedded as variable.",
)
def export_command(
    test_cases_file: Path | None,
    format: str,
    output: Path | None,
    collection_name: str | None,
    base_url: str,
) -> None:
    """Deterministically transform generated test cases into runnable test artifacts
    (Postman Collections and REST Client .http files).
    """
    try:
        target_format = ExportFormat(format.lower())
    except ValueError:
        click.echo(f"Error: Invalid format '{format}'.", err=True)
        sys.exit(1)

    # Validate that dual format requires an explicit output directory before reading stdin/file
    if target_format == ExportFormat.BOTH and output is None:
        click.echo(
            "Error: Option '--output <directory>' is required when '--format both' is specified.",
            err=True,
        )
        sys.exit(1)

    if test_cases_file is None and sys.stdin.isatty():
        click.echo(
            "Error: No test cases provided. Pass a file argument or pipe JSONL via stdin.",
            err=True,
        )
        sys.exit(1)

    try:
        test_cases = read_test_cases(test_cases_file)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error reading test cases: {exc}", err=True)
        sys.exit(1)

    config = ExportConfig(
        format=target_format,
        output_path=output,
        collection_name=collection_name,
        base_url=base_url,
    )

    try:
        export_batch(test_cases, config, out_stream=sys.stdout, err_stream=sys.stderr)
    except Exception as exc:
        click.echo(f"Error during export: {exc}", err=True)
        sys.exit(1)

    sys.exit(0)


@cli.command("audit")
@click.argument(
    "artifact_file",
    required=False,
    default=None,
    type=click.Path(allow_dash=True),
)
@click.option(
    "--index-dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Directory of indexed Qdrant database (or SPECPROBE_INDEX_DIR).",
)
@click.option(
    "--spec",
    "spec_file",
    type=click.Path(dir_okay=False),
    default=None,
    help="Optional direct path to an OpenAPI 3.0/3.1 YAML or JSON specification file.",
)
@click.option(
    "--summary",
    is_flag=True,
    default=False,
    help="Render human-readable summary table of coverage metrics to stderr.",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Bypass LLM disk cache when generating semantic assertion critiques.",
)
@click.option(
    "--model",
    type=str,
    default=None,
    help="Model identifier string passed to LiteLLM (or SPECPROBE_LLM_MODEL).",
)
@click.option(
    "--api-base",
    type=str,
    default=None,
    help="Base endpoint URL for model requests (or SPECPROBE_LLM_API_BASE).",
)
@click.option(
    "--cache-dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Directory for caching LLM audit critique responses (or SPECPROBE_AUDIT_CACHE_DIR).",
)
def audit_command(
    artifact_file: str | None,
    index_dir: str | None,
    spec_file: str | None,
    summary: bool,
    no_cache: bool,
    model: str | None,
    api_base: str | None,
    cache_dir: str | None,
) -> None:
    """Compare an API specification against existing test artifacts (Postman Collections or
    REST Client .http files) to perform gap analysis and evaluate assertion quality.
    """
    if artifact_file is None:
        if sys.stdin.isatty():
            click.echo(
                "Error: No test artifact provided. Pass a file argument or pipe via stdin.",
                err=True,
            )
            sys.exit(1)
        artifact_file = "-"

    resolved_index_dir = index_dir or os.environ.get("SPECPROBE_INDEX_DIR", ".specprobe/index")
    resolved_cache_dir = cache_dir or os.environ.get(
        "SPECPROBE_AUDIT_CACHE_DIR", ".specprobe/cache/audit"
    )

    try:
        chunks, spec_source = load_spec_chunks(spec_path=spec_file, index_dir=resolved_index_dir)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except SpecLoadError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error loading specification: {exc}", err=True)
        sys.exit(1)

    try:
        items, artifact_source = load_artifact_items(artifact_path=artifact_file)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error loading test artifact: {exc}", err=True)
        sys.exit(1)

    try:
        gateway = LLMGateway(model=model, api_base=api_base)
    except Exception as exc:
        click.echo(f"Error initializing LLM gateway: {exc}", err=True)
        sys.exit(1)

    engine = AuditEngine(
        gateway=gateway,
        cache_dir=resolved_cache_dir,
        no_cache=no_cache,
    )

    try:
        engine.audit(
            chunks=chunks,
            test_items=items,
            spec_source=spec_source,
            artifact_source=artifact_source,
            stream_stdout=True,
            out_stream=sys.stdout,
            err_stream=sys.stderr,
            render_summary=summary,
        )
    except Exception as exc:
        click.echo(f"Error: Audit execution failed: {exc}", err=True)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    cli()
