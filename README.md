# specprobe

A CLI that turns an OpenAPI spec into a searchable, locally-indexed knowledge base and generates schema-validated API test cases from it — no cloud calls required unless you opt in.

```
spec.yaml → chunk → index → search → generate
           (parse)  (embed)  (retrieve)  (LLM + validate)
```

## What it does

**`chunk`** — Deterministically decomposes an OpenAPI 3.0/3.1 spec into one self-contained JSON object per operation: method, path, merged parameters, pruned `$ref`-resolved schemas, tags, security requirements, and a token estimate. No LLM involved — same spec in, same chunks out, every time.

**`index`** — Embeds each chunk (dense + BM25 sparse vectors, via local ONNX models through FastEmbed) into an on-disk Qdrant collection. Runs fully offline; no spec text or embeddings ever leave the machine.

**`search`** — Natural-language retrieval over the index, in three modes: `dense` (cosine similarity), `hybrid` (dense + sparse fused with RRF), or `hybrid-rerank` (hybrid retrieval + local cross-encoder reranking). Supports metadata filters (`--tag`, `--method`, `--deprecated`, `--source-title`, `--source-version`).

**`generate`** — Takes `search --full` output and asks an LLM to produce a happy-path test case per operation: concrete request fixtures, expected status/headers, and a schema-shape assertion. Every output is validated against a strict Pydantic schema; a validation failure triggers exactly one self-correcting retry with the error fed back to the model, then the operation is marked failed and the batch continues. Calls are cached to disk (SHA-256 of messages + model + temperature) so repeat runs and CI are zero-cost and don't need a live model.

## Design principles

- **Local-first by default.** Embeddings and reranking always run on-device. The LLM gateway defaults to a local LM Studio endpoint (`http://localhost:1234/v1`) with no API key required; cloud providers (OpenAI, Anthropic, Gemini) are strictly opt-in and refuse to run without the matching `*_API_KEY` env var.
- **Deterministic where it can be.** Chunking and (eventually) exported test artifacts are pure parsing/templating — no LLM, no drift, reproducible byte-for-byte.
- **One gateway.** All model calls route through [LiteLLM](https://github.com/BerriAI/litellm), so switching between local and cloud models is a `--model`/`--api-base` flag, not a code change.

Full rationale lives in [`.specify/memory/constitution.md`](.specify/memory/constitution.md).

## Install

Requires Python 3.11+. Dependency management is [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run specprobe --help
```

## Quickstart

```bash
# 1. Chunk a spec
uv run specprobe chunk petstore.yaml > chunks.jsonl

# 2. Build the local index
uv run specprobe index chunks.jsonl

# 3. Search it
uv run specprobe search "cancel a pending order" --mode hybrid-rerank --limit 3

# 4. Generate validated test cases from semantic search matches
uv run specprobe search "cancel a pending order" --full --limit 3 \
  | uv run specprobe generate

# 5. Spec-wide generation: extract an entire spec unranked and generate tests for all operations
uv run specprobe search --source-title "Petstore API" --full \
  | uv run specprobe generate
```

`generate` streams one JSON Lines object per successful test case to stdout and per-operation error diagnostics to stderr, so it composes with the rest of the pipeline and with CI without extra plumbing.

## CLI reference

| Command | Purpose | Key options |
|---|---|---|
| `chunk <spec_file>` | Parse a spec into JSONL chunks | `--schema-depth`, `--max-tokens`, `--op <id>` (spot-check one operation), `--stats` (summary table instead of chunks) |
| `index [chunk_file]` | Ingest chunks into the vector store (file arg or stdin) | `--index-dir`, `--stats` (collection health/counts) |
| `search [query]` | Natural-language retrieval or unranked filter-only spec extraction | `--mode {dense,hybrid,hybrid-rerank}`, `-n/--limit`, `--tag`, `--method`, `--deprecated/--no-deprecated`, `--source-title`, `--source-version`, `--full` |
| `generate [results_file]` | LLM test-case generation from search results (file arg or stdin) | `--model`, `--api-base`, `--temperature`, `--cache-dir`, `--no-cache` |

When `search` is called without a `<query>`, it operates in filter-only mode: all operations matching the provided metadata filter(s) are retrieved unranked (`score: 0.0`) with unlimited pagination by default (or respecting explicit `-n/--limit`). Either `<query>` or at least one metadata filter must be provided.

Every command also accepts input via stdin where a file argument is optional, so the four stages pipe directly into each other.

## Configuration

All `generate` flags can be set via environment variable instead (flag takes precedence):

| Env var | Default |
|---|---|
| `SPECPROBE_LLM_MODEL` | `openai/local-model` |
| `SPECPROBE_LLM_API_BASE` | `http://localhost:1234/v1` |
| `SPECPROBE_LLM_API_KEY` | *(none)* |
| `SPECPROBE_LLM_TEMPERATURE` | `0.0` |
| `SPECPROBE_CACHE_DIR` | `.specprobe/cache` |
| `SPECPROBE_NO_CACHE` | `false` |
| `SPECPROBE_INDEX_DIR` | `.specprobe/index` |

To use a cloud model, set `--model openai/gpt-4o` (or `anthropic/...`, `gemini/...`) and the corresponding `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` — omitting the key fails fast with an explanatory error rather than silently falling back.

## Development

```bash
uv run pytest          # full suite
uv run ruff check .    # lint
uv run ruff format .   # format
```

Feature work follows a spec-first workflow — see `specs/` for the spec, plan, and task breakdown behind each feature, and `.specify/memory/constitution.md` for the constraints every change is checked against.

## Project layout

```
src/specprobe/
├── chunker/     # OpenAPI parsing, schema pruning, token estimation
├── index/       # FastEmbed embedding + Qdrant storage
├── search/      # Multi-mode retrieval engine
├── generator/   # LLM gateway, prompt synthesis, validation/retry, disk cache
├── formatters/  # Output serialization (JSONL, etc.)
├── models.py    # Shared Pydantic models
└── cli.py       # Click command group
```

## License

Apache 2.0 — see [LICENSE](LICENSE).
