"""Deterministic structural gap analysis and LLM prompt assembly for API test artifacts."""

from typing import Any

from specprobe.audit.matcher import match_operation
from specprobe.audit.models import (
    ArtifactTestItem,
    AuditReport,
    CoverageGap,
    CoverageGapSeverity,
    CoverageGapType,
    OperationCritique,
)
from specprobe.chunker.models import OperationChunk

__all__ = [
    "analyze_structural_gaps",
    "build_audit_critique_prompt",
]


def _extract_documented_statuses(responses: dict[str, Any]) -> list[int]:
    """Extract integer HTTP status codes from an OpenAPI responses dictionary."""
    codes: list[int] = []
    for key in responses.keys():
        try:
            code = int(key)
            codes.append(code)
        except ValueError:
            pass
    return sorted(codes)


def analyze_structural_gaps(
    chunks: list[OperationChunk],
    test_items: list[ArtifactTestItem],
    spec_source: str = "",
    artifact_source: str = "",
) -> AuditReport:
    """Perform zero-LLM deterministic gap analysis comparing spec operations and test items.

    Identifies untested operations, unexercised status codes, omitted parameters,
    and phantom test requests without external network or LLM calls.
    """
    # Map matched test items by operation
    matched_by_op: dict[str, list[ArtifactTestItem]] = {}
    matched_item_ids: set[int] = set()

    for chunk in chunks:
        op_id = str(chunk.operation.get("operationId") or chunk.metadata.operationId)
        matched_items: list[ArtifactTestItem] = []
        for idx, item in enumerate(test_items):
            if match_operation(chunk.metadata.method, chunk.metadata.path, item):
                matched_items.append(item)
                matched_item_ids.add(idx)
        matched_by_op[op_id] = matched_items

    operation_critiques: list[OperationCritique] = []

    for chunk in chunks:
        op_id = str(chunk.operation.get("operationId") or chunk.metadata.operationId)
        method = chunk.metadata.method.upper()
        path = chunk.metadata.path
        matched = matched_by_op.get(op_id, [])

        responses = chunk.operation.get("responses", {})
        documented_statuses = _extract_documented_statuses(responses)
        tested_statuses = sorted(
            list({item.expected_status for item in matched if item.expected_status is not None})
        )
        untested_statuses = [c for c in documented_statuses if c not in tested_statuses]

        gaps: list[CoverageGap] = []

        if not matched:
            # Operation completely untested
            gaps.append(
                CoverageGap(
                    gap_type=CoverageGapType.MISSING_OPERATION,
                    severity=CoverageGapSeverity.CRITICAL,
                    target=op_id,
                    description=f"Operation '{op_id}' has no corresponding test in artifact.",
                    recommendation=f"Add test scenarios exercising {method} {path}.",
                )
            )
            # All documented status codes are unexercised
            for s_code in documented_statuses:
                gaps.append(
                    CoverageGap(
                        gap_type=CoverageGapType.MISSING_STATUS_CODE,
                        severity=CoverageGapSeverity.CRITICAL
                        if 200 <= s_code < 300
                        else CoverageGapSeverity.WARNING,
                        target=str(s_code),
                        description=f"Status code {s_code} has no test coverage.",
                        recommendation=f"Add a scenario asserting HTTP {s_code}.",
                    )
                )
            critique = OperationCritique(
                operation_id=op_id,
                method=method,
                path=path,
                matched_tests_count=0,
                documented_status_codes=documented_statuses,
                tested_status_codes=[],
                untested_status_codes=documented_statuses,
                gaps=gaps,
                assertion_quality_score=0.0,
                critique_summary=f"Operation '{op_id}' is completely uncovered by tests.",
            )
        else:
            # Unexercised status codes
            for s_code in untested_statuses:
                sev = (
                    CoverageGapSeverity.CRITICAL
                    if 200 <= s_code < 300
                    else CoverageGapSeverity.WARNING
                )
                gaps.append(
                    CoverageGap(
                        gap_type=CoverageGapType.MISSING_STATUS_CODE,
                        severity=sev,
                        target=str(s_code),
                        description=(
                            f"Operation documents HTTP {s_code} response, "
                            "but no test exercises this status code."
                        ),
                        recommendation=f"Add a test scenario asserting HTTP {s_code}.",
                    )
                )

            # Untested parameters
            params = chunk.operation.get("parameters", [])
            for p in params:
                if isinstance(p, dict):
                    p_name = str(p.get("name", ""))
                    p_in = str(p.get("in", ""))
                    is_req = bool(p.get("required"))
                    if p_in in ("query", "header"):
                        is_tested = any(
                            p_name in item.query_params or p_name in item.headers
                            for item in matched
                        )
                        if not is_tested:
                            p_sev = (
                                CoverageGapSeverity.WARNING
                                if is_req
                                else CoverageGapSeverity.SUGGESTION
                            )
                            gaps.append(
                                CoverageGap(
                                    gap_type=CoverageGapType.MISSING_PARAMETER,
                                    severity=p_sev,
                                    target=p_name,
                                    description=(
                                        f"Documented {p_in} parameter '{p_name}' "
                                        "is not exercised by any matched test."
                                    ),
                                    recommendation=(
                                        f"Add test requests including the '{p_name}' parameter."
                                    ),
                                )
                            )

            # Assertion quality evaluation
            has_schema = any(item.has_schema_assertion for item in matched)
            has_props = any(item.has_property_assertions for item in matched)

            if has_schema:
                base_score = 0.85
            elif has_props:
                base_score = 0.60
                gaps.append(
                    CoverageGap(
                        gap_type=CoverageGapType.WEAK_ASSERTION,
                        severity=CoverageGapSeverity.SUGGESTION,
                        target=op_id,
                        description=(
                            f"Tests for '{op_id}' check property existence, but lack "
                            "complete JSON Schema validation."
                        ),
                        recommendation=(
                            "Upgrade test assertions to pm.response.to.have.jsonSchema(...) "
                            "or schema signature validation."
                        ),
                    )
                )
            else:
                base_score = 0.40
                gaps.append(
                    CoverageGap(
                        gap_type=CoverageGapType.WEAK_ASSERTION,
                        severity=CoverageGapSeverity.SUGGESTION,
                        target=op_id,
                        description=(
                            f"Tests for '{op_id}' only verify status code, without "
                            "validating response body or schema."
                        ),
                        recommendation=(
                            "Add response body assertions or JSON Schema validation "
                            "to verify response contract."
                        ),
                    )
                )

            # Adjust score by status code coverage
            if documented_statuses:
                ratio = len(tested_statuses) / len(documented_statuses)
                final_score = round(max(0.1, min(1.0, base_score * (0.5 + 0.5 * ratio))), 2)
            else:
                final_score = base_score

            summary_notes: list[str] = [f"{len(matched)} test request(s) match this operation."]
            if untested_statuses:
                summary_notes.append(f"Untested status codes: {untested_statuses}.")
            if has_schema:
                summary_notes.append("Response structure is validated with JSON Schema.")
            elif has_props:
                summary_notes.append("Only shallow property presence is verified.")
            else:
                summary_notes.append("Only status codes are asserted without schema validation.")

            critique = OperationCritique(
                operation_id=op_id,
                method=method,
                path=path,
                matched_tests_count=len(matched),
                documented_status_codes=documented_statuses,
                tested_status_codes=tested_statuses,
                untested_status_codes=untested_statuses,
                gaps=gaps,
                assertion_quality_score=final_score,
                critique_summary=" ".join(summary_notes),
            )

        operation_critiques.append(critique)

    # Detect phantom tests (tests in artifact that do not correspond to any spec operation)
    phantom_items = [item for idx, item in enumerate(test_items) if idx not in matched_item_ids]
    for phantom in phantom_items:
        p_name = phantom.name or f"{phantom.method} {phantom.path}"
        phantom_gap = CoverageGap(
            gap_type=CoverageGapType.PHANTOM_TEST,
            severity=CoverageGapSeverity.WARNING,
            target=phantom.path,
            description=(
                f"Test request '{p_name}' ({phantom.method} {phantom.path}) does not "
                "match any operation defined in the specification."
            ),
            recommendation=(
                "Verify whether this operation was removed from the specification "
                "or if the test URL is outdated."
            ),
        )
        operation_critiques.append(
            OperationCritique(
                operation_id=f"phantom_{phantom.method}_{phantom.path}",
                method=phantom.method,
                path=phantom.path,
                matched_tests_count=1,
                documented_status_codes=[],
                tested_status_codes=[phantom.expected_status] if phantom.expected_status else [],
                untested_status_codes=[],
                gaps=[phantom_gap],
                assertion_quality_score=0.0,
                critique_summary=(
                    "Orphaned test request does not match any operation in the specification."
                ),
            )
        )

    # Compute overall statistics
    total_spec_ops = len(chunks)
    covered_ops = sum(
        1
        for c in operation_critiques
        if c.matched_tests_count > 0 and not c.operation_id.startswith("phantom_")
    )
    op_cov_pct = round((covered_ops / total_spec_ops * 100.0) if total_spec_ops > 0 else 0.0, 2)

    total_doc_statuses = sum(len(c.documented_status_codes) for c in operation_critiques)
    covered_doc_statuses = sum(
        len(c.tested_status_codes)
        for c in operation_critiques
        if not c.operation_id.startswith("phantom_")
    )
    status_cov_pct = round(
        (covered_doc_statuses / total_doc_statuses * 100.0) if total_doc_statuses > 0 else 0.0, 2
    )

    all_gaps = [g for c in operation_critiques for g in c.gaps]
    gaps_by_sev: dict[str, int] = {}
    for g in all_gaps:
        gaps_by_sev[g.severity] = gaps_by_sev.get(g.severity, 0) + 1

    return AuditReport(
        spec_source=spec_source,
        artifact_source=artifact_source,
        total_spec_operations=total_spec_ops,
        covered_operations=covered_ops,
        operation_coverage_pct=op_cov_pct,
        total_documented_statuses=total_doc_statuses,
        covered_documented_statuses=covered_doc_statuses,
        status_coverage_pct=status_cov_pct,
        total_gaps=len(all_gaps),
        gaps_by_severity=gaps_by_sev,
        operation_critiques=operation_critiques,
    )


def build_audit_critique_prompt(
    chunk: OperationChunk,
    matched_tests: list[ArtifactTestItem],
    existing_gaps: list[CoverageGap],
) -> str:
    """Assemble an informative prompt for LLM semantic assertion critique."""
    op_id = str(chunk.operation.get("operationId") or chunk.metadata.operationId)
    method = chunk.metadata.method.upper()
    path = chunk.metadata.path

    lines: list[str] = [
        f"Operation: {method} {path}",
        f"Operation ID: {op_id}",
    ]

    if chunk.operation.get("summary"):
        lines.append(f"Summary: {chunk.operation['summary']}")

    responses = chunk.operation.get("responses", {})
    if responses:
        lines.append("Documented Responses:")
        for code, resp in responses.items():
            desc = resp.get("description", "") if isinstance(resp, dict) else str(resp)
            lines.append(f"  - {code}: {desc}")

    params = chunk.operation.get("parameters", [])
    if params:
        lines.append("Documented Parameters:")
        for p in params:
            lines.append(f"  - {p.get('name')} ({p.get('in')}, required: {p.get('required')})")

    lines.append("\nExisting Matched Tests in Artifact:")
    if not matched_tests:
        lines.append("  (None)")
    else:
        for idx, t in enumerate(matched_tests, 1):
            name_str = f" - '{t.name}'" if t.name else ""
            status_str = f" - Expected Status: {t.expected_status}" if t.expected_status else ""
            schema_str = " (Has JSON Schema assertion)" if t.has_schema_assertion else ""
            props_str = " (Has property assertions)" if t.has_property_assertions else ""
            lines.append(
                f"  {idx}. {t.method} {t.path}{name_str}{status_str}{schema_str}{props_str}"
            )

    if existing_gaps:
        lines.append("\nDetected Structural Gaps:")
        for g in existing_gaps:
            lines.append(f"  - [{g.severity.upper()}] {g.gap_type}: {g.description}")

    lines.append("\nProvide your assertion quality critique JSON now:")
    return "\n".join(lines)
