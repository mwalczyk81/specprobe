"""Audit engine orchestrating spec retrieval, artifact parsing, gap analysis, and LLM critique."""

import json
import sys
from pathlib import Path
from typing import Any

from specprobe.audit.analyzer import (
    analyze_structural_gaps,
    build_audit_critique_prompt,
)
from specprobe.audit.matcher import match_operation
from specprobe.audit.models import (
    ArtifactTestItem,
    AuditReport,
    CoverageGap,
    CoverageGapSeverity,
    CoverageGapType,
    OperationCritique,
)
from specprobe.audit.parser import parse_artifact
from specprobe.chunker.extractor import OperationExtractor
from specprobe.chunker.loader import load_openapi_spec
from specprobe.chunker.models import OperationChunk
from specprobe.generator.cache import DiskCache
from specprobe.generator.engine import _extract_json_object
from specprobe.generator.gateway import LLMGateway
from specprobe.index.store import QdrantIndexStore

__all__ = [
    "AuditEngine",
    "load_artifact_items",
    "load_audit_prompt",
    "load_spec_chunks",
    "render_summary_table",
]

DEFAULT_AUDIT_SYSTEM_PROMPT = """You are an expert API testing auditor and quality reviewer.
Your role is to analyze test coverage and assertion strength of existing test requests
against an OpenAPI operation.

You will be given:
1. The OpenAPI specification for an operation (path, method, parameters, request body, responses).
2. The existing test requests executed against this operation (from Postman or .http file).
3. The deterministic structural gaps already detected (e.g. unexercised status codes).

Your task is to provide:
1. An evaluation of test assertion quality and depth.
2. An assertion quality score between 0.0 and 1.0 (where 0.0 = completely untested,
   0.4 = status code only, 0.7 = status + properties, 1.0 = strict JSON schema + headers).
3. Recommendations for improving assertion strength and validating schema constraints.
4. A concise narrative critique summary.

You MUST output ONLY a valid JSON object matching the following structure
without any markdown code fences, commentary, or preamble:

{
  "operation_id": "<exact operation identifier>",
  "assertion_quality_score": 0.75,
  "critique_summary": "<concise summary of test coverage and assertion depth>",
  "gaps": [
    {
      "gap_type": "weak_assertion",
      "severity": "suggestion",
      "target": "<target identifier>",
      "description": "<detailed description of the weakness or gap>",
      "recommendation": "<concrete actionable guidance to resolve the gap>"
    }
  ]
}
"""


def load_audit_prompt() -> str:
    """Load audit prompt template from prompts/audit.md if available, else return default."""
    prompt_file = Path("prompts/audit.md")
    if prompt_file.exists():
        try:
            return prompt_file.read_text(encoding="utf-8")
        except Exception:
            pass
    return DEFAULT_AUDIT_SYSTEM_PROMPT


def load_spec_chunks(
    spec_path: str | Path | None = None,
    index_dir: str | Path | None = None,
) -> tuple[list[OperationChunk], str]:
    """Retrieve operation chunks either directly from an OpenAPI spec or from a Qdrant index.

    Parameters
    ----------
    spec_path : str | Path | None
        Path to an OpenAPI 3.0/3.1 YAML/JSON specification.
    index_dir : str | Path | None
        Directory of the indexed Qdrant vector database.

    Returns
    -------
    tuple[list[OperationChunk], str]
        List of extracted operation chunks and the human-readable source label.

    Raises
    ------
    FileNotFoundError
        If the specified spec file or index directory does not exist.
    ValueError
        If no operations are found or the index is uninitialized.
    """
    if spec_path:
        p = Path(spec_path)
        if not p.exists():
            raise FileNotFoundError(f"Specification file '{spec_path}' does not exist.")
        raw_spec = load_openapi_spec(p)
        extractor = OperationExtractor(raw_spec)
        chunks = list(extractor.extract_operations())
        title = raw_spec.get("info", {}).get("title", "OpenAPI Specification")
        return chunks, f"{spec_path} ({title})"

    resolved_index = Path(index_dir or ".specprobe/index")
    if not resolved_index.exists():
        raise FileNotFoundError(
            f"Index directory '{resolved_index}' does not exist. "
            "Run 'specprobe index' to create an index, or provide '--spec <path>'."
        )

    with QdrantIndexStore(index_path=resolved_index) as store:
        if not store.client.collection_exists(store.collection_name):
            raise ValueError(
                f"No vector collection '{store.collection_name}' found at '{resolved_index}'. "
                "Run 'specprobe index' to index your specification, or provide '--spec <path>'."
            )

        records, _ = store.client.scroll(
            collection_name=store.collection_name,
            limit=5000,
            with_payload=True,
            with_vectors=False,
        )

        chunks: list[OperationChunk] = []
        titles: set[str] = set()
        for rec in records:
            payload = rec.payload or {}
            raw_chunk = payload.get("raw_chunk")
            if raw_chunk:
                try:
                    chunk = OperationChunk.model_validate(raw_chunk)
                    chunks.append(chunk)
                    titles.add(chunk.metadata.source_title)
                except Exception:
                    pass

        if not chunks:
            raise ValueError(
                f"Vector index at '{resolved_index}' contains 0 operations. "
                "Run 'specprobe index' to index a specification, or provide '--spec <path>'."
            )

        title_str = ", ".join(sorted(titles)) if titles else "Indexed API"
        return chunks, f"{resolved_index} ({title_str})"


def load_artifact_items(
    artifact_path: str | Path | None = None,
    stdin_content: str | None = None,
) -> tuple[list[ArtifactTestItem], str]:
    """Parse test requests from a Postman Collection JSON or REST Client .http file.

    Parameters
    ----------
    artifact_path : str | Path | None
        Path to test artifact, or '-' for stdin.
    stdin_content : str | None
        Pre-read stdin string content for testing.

    Returns
    -------
    tuple[list[ArtifactTestItem], str]
        List of parsed test items and the source identifier label.
    """
    if artifact_path is None or str(artifact_path) == "-":
        content = stdin_content if stdin_content is not None else sys.stdin.read()
        if not content.strip():
            return [], "stdin"
        items = parse_artifact(content)
        return items, "stdin"

    p = Path(artifact_path)
    if not p.exists():
        raise FileNotFoundError(f"Artifact file '{artifact_path}' does not exist.")

    items = parse_artifact(p)
    return items, str(artifact_path)


def render_summary_table(
    report: AuditReport,
    err_stream: Any = None,
) -> None:
    """Render a formatted human-readable summary table of coverage metrics to stderr."""
    stream = err_stream if err_stream is not None else sys.stderr

    # Collect sample gap descriptions for summary
    critical_samples: list[str] = []
    warning_samples: list[str] = []
    suggestion_samples: list[str] = []

    for critique in report.operation_critiques:
        for g in critique.gaps:
            if g.severity == CoverageGapSeverity.CRITICAL:
                if g.gap_type == CoverageGapType.MISSING_OPERATION:
                    critical_samples.append(f"Untested operation: {g.target}")
                else:
                    critical_samples.append(f"Status {g.target}")
            elif g.severity == CoverageGapSeverity.WARNING:
                if g.gap_type == CoverageGapType.MISSING_STATUS_CODE:
                    warning_samples.append(f"Status {g.target}")
                elif g.gap_type == CoverageGapType.MISSING_PARAMETER:
                    warning_samples.append(f"Param '{g.target}'")
                elif g.gap_type == CoverageGapType.PHANTOM_TEST:
                    warning_samples.append(f"Phantom {g.target}")
            elif g.severity == CoverageGapSeverity.SUGGESTION:
                suggestion_samples.append(f"Weak assertion: {g.target}")

    crit_count = report.gaps_by_severity.get(CoverageGapSeverity.CRITICAL, 0)
    warn_count = report.gaps_by_severity.get(CoverageGapSeverity.WARNING, 0)
    sugg_count = report.gaps_by_severity.get(CoverageGapSeverity.SUGGESTION, 0)

    crit_detail = f"  ({', '.join(critical_samples[:3])})" if critical_samples else ""
    warn_detail = f"  ({', '.join(warning_samples[:3])})" if warning_samples else ""
    sugg_detail = f"  ({', '.join(suggestion_samples[:3])})" if suggestion_samples else ""

    lines = [
        "============================= SpecProbe Audit Summary =============================",
        f"Specification: {report.spec_source}",
        f"Artifact:      {report.artifact_source}",
        "",
        "Coverage Metrics:",
        (
            f"  Operations:      {report.covered_operations} / "
            f"{report.total_spec_operations} covered ({report.operation_coverage_pct:.1f}%)"
        ),
        (
            f"  Status Codes:    {report.covered_documented_statuses} / "
            f"{report.total_documented_statuses} exercised ({report.status_coverage_pct:.1f}%)"
        ),
        "",
        "Coverage Gaps by Severity:",
        f"  [CRITICAL]    {crit_count:<4}{crit_detail}",
        f"  [WARNING]     {warn_count:<4}{warn_detail}",
        f"  [SUGGESTION]  {sugg_count:<4}{sugg_detail}",
        "",
        f"Total Gaps:    {report.total_gaps}",
        "===================================================================================",
    ]
    stream.write("\n".join(lines) + "\n")
    stream.flush()


class AuditEngine:
    """Audit engine coordinating artifact parsing, deterministic diffing, and LLM critique."""

    def __init__(
        self,
        gateway: LLMGateway | None = None,
        cache: DiskCache | None = None,
        cache_dir: str | Path = ".specprobe/cache/audit",
        no_cache: bool = False,
    ) -> None:
        self.gateway = gateway
        self.cache = (
            cache if cache is not None else DiskCache(cache_dir=cache_dir, no_cache=no_cache)
        )

    def _critique_with_llm(
        self,
        chunk: OperationChunk,
        matched_items: list[ArtifactTestItem],
        initial_critique: OperationCritique,
    ) -> OperationCritique:
        """Call the LLM gateway with caching and self-correction to critique assertion depth."""
        if not self.gateway:
            return initial_critique

        system_prompt = load_audit_prompt()
        user_prompt = build_audit_critique_prompt(chunk, matched_items, initial_critique.gaps)
        initial_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # First attempt
        raw_completion = self.gateway.complete(initial_messages, cache=self.cache)
        try:
            data = _extract_json_object(raw_completion)
        except (ValueError, json.JSONDecodeError) as first_exc:
            # Self-correcting retry exactly once
            retry_messages = list(initial_messages)
            retry_messages.append({"role": "assistant", "content": raw_completion})
            retry_messages.append(
                {
                    "role": "user",
                    "content": (
                        f"The previous output was not a valid JSON object: {first_exc}\n"
                        "Please fix and return ONLY valid JSON matching the required schema."
                    ),
                }
            )
            retry_completion = self.gateway.complete(retry_messages, cache=self.cache)
            data = _extract_json_object(retry_completion)

        # Merge critique findings
        if "assertion_quality_score" in data:
            try:
                score = float(data["assertion_quality_score"])
                initial_critique.assertion_quality_score = max(0.0, min(1.0, score))
            except (ValueError, TypeError):
                pass

        if "critique_summary" in data and data["critique_summary"]:
            initial_critique.critique_summary = str(data["critique_summary"])

        if "gaps" in data and isinstance(data["gaps"], list):
            for g in data["gaps"]:
                if isinstance(g, dict):
                    try:
                        parsed_gap = CoverageGap.model_validate(g)
                        # Check duplicate
                        if not any(
                            existing.gap_type == parsed_gap.gap_type
                            and existing.target == parsed_gap.target
                            for existing in initial_critique.gaps
                        ):
                            initial_critique.gaps.append(parsed_gap)
                    except Exception:
                        pass

        return initial_critique

    def audit(
        self,
        chunks: list[OperationChunk],
        test_items: list[ArtifactTestItem],
        spec_source: str = "",
        artifact_source: str = "",
        stream_stdout: bool = True,
        out_stream: Any = None,
        err_stream: Any = None,
        render_summary: bool = False,
    ) -> AuditReport:
        """Execute full audit analysis and stream JSONL critique records to output.

        Parameters
        ----------
        chunks : list[OperationChunk]
            OpenAPI specification operation chunks.
        test_items : list[ArtifactTestItem]
            Extracted test items from test artifact.
        spec_source : str
            Specification source description.
        artifact_source : str
            Artifact source description.
        stream_stdout : bool
            Whether to stream OperationCritique JSONL to out_stream.
        out_stream : Any | None
            Output stream for JSONL (defaults to sys.stdout).
        err_stream : Any | None
            Error/diagnostic stream (defaults to sys.stderr).
        render_summary : bool
            Whether to render coverage metrics table to err_stream.

        Returns
        -------
        AuditReport
            Aggregated audit report.
        """
        if out_stream is None:
            out_stream = sys.stdout
        if err_stream is None:
            err_stream = sys.stderr

        # 1. Deterministic structural diff (Constitution Principle II: zero LLM)
        report = analyze_structural_gaps(
            chunks=chunks,
            test_items=test_items,
            spec_source=spec_source,
            artifact_source=artifact_source,
        )

        if not test_items:
            err_stream.write(
                f"Notice: Artifact '{artifact_source}' contains 0 test requests. "
                f"All {len(chunks)} specification operations reported as uncovered.\n"
            )
            err_stream.flush()

        # 2. Per-operation LLM semantic critique for operations with matched tests
        chunk_map = {
            str(c.operation.get("operationId") or c.metadata.operationId): c for c in chunks
        }

        updated_critiques: list[OperationCritique] = []
        for critique in report.operation_critiques:
            if (
                critique.matched_tests_count > 0
                and not critique.operation_id.startswith("phantom_")
                and self.gateway is not None
            ):
                chunk = chunk_map.get(critique.operation_id)
                if chunk:
                    matched = [
                        item
                        for item in test_items
                        if match_operation(chunk.metadata.method, chunk.metadata.path, item)
                    ]
                    critique = self._critique_with_llm(chunk, matched, critique)

            updated_critiques.append(critique)
            if stream_stdout:
                out_stream.write(critique.model_dump_json() + "\n")
                out_stream.flush()

        report.operation_critiques = updated_critiques

        # Recalculate gaps
        all_gaps = [g for c in updated_critiques for g in c.gaps]
        report.total_gaps = len(all_gaps)
        gaps_by_sev: dict[str, int] = {}
        for g in all_gaps:
            gaps_by_sev[g.severity] = gaps_by_sev.get(g.severity, 0) + 1
        report.gaps_by_severity = gaps_by_sev

        # 3. Render summary table if requested
        if render_summary:
            render_summary_table(report, err_stream=err_stream)

        return report
