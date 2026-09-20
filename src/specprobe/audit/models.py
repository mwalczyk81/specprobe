"""Pydantic data models for test artifact audit and gap analysis."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ArtifactTestItem",
    "AuditReport",
    "CoverageGap",
    "CoverageGapSeverity",
    "CoverageGapType",
    "OperationCritique",
]


class CoverageGapType(StrEnum):
    """Classification of coverage gaps identified during audit."""

    MISSING_OPERATION = "missing_operation"
    MISSING_STATUS_CODE = "missing_status_code"
    MISSING_PARAMETER = "missing_parameter"
    WEAK_ASSERTION = "weak_assertion"
    PHANTOM_TEST = "phantom_test"


class CoverageGapSeverity(StrEnum):
    """Severity classification for audit coverage gaps."""

    CRITICAL = "critical"
    WARNING = "warning"
    SUGGESTION = "suggestion"


class CoverageGap(BaseModel):
    """A specific gap or deficiency identified between specification and test artifact."""

    model_config = ConfigDict(extra="ignore")

    gap_type: CoverageGapType = Field(
        description="Type of coverage gap.",
    )
    severity: CoverageGapSeverity = Field(
        description="Severity rating of the gap.",
    )
    target: str = Field(
        description="Target identifier (e.g. operation_id, status code, or parameter name).",
    )
    description: str = Field(
        description="Detailed description of the deficiency.",
    )
    recommendation: str = Field(
        description="Actionable guidance to remediate the gap.",
    )


class ArtifactTestItem(BaseModel):
    """Normalized test request item extracted from a Postman Collection or REST Client
    (.http) file.
    """

    model_config = ConfigDict(extra="ignore")

    name: str = Field(
        default="",
        description="Name or label of the test item.",
    )
    method: str = Field(
        description="HTTP method (e.g. GET, POST, PUT, DELETE).",
    )
    path: str = Field(
        description="Request path or path template (e.g. /pets/{{petId}} or /pets/1).",
    )
    query_params: list[str] = Field(
        default_factory=list,
        description="Query parameter keys present in the test request.",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Request headers present in the test request.",
    )
    has_body: bool = Field(
        default=False,
        description="Whether the request provides a body payload.",
    )
    expected_status: int | None = Field(
        default=None,
        description="Expected HTTP status code asserted in scripts or comments.",
    )
    has_schema_assertion: bool = Field(
        default=False,
        description="Whether test asserts response JSON Schema structure.",
    )
    has_property_assertions: bool = Field(
        default=False,
        description="Whether test asserts response property existence.",
    )
    raw_source: str = Field(
        default="",
        description="Reference to source file or location of the test item.",
    )


class OperationCritique(BaseModel):
    """Structured audit assessment and critique for a single OpenAPI operation."""

    model_config = ConfigDict(extra="ignore")

    operation_id: str = Field(
        description="Identifier of the target API operation.",
    )
    method: str = Field(
        description="HTTP method of the target operation.",
    )
    path: str = Field(
        description="Path template of the target operation.",
    )
    matched_tests_count: int = Field(
        default=0,
        description="Number of test requests matching this operation.",
    )
    documented_status_codes: list[int] = Field(
        default_factory=list,
        description="HTTP status codes documented in the specification.",
    )
    tested_status_codes: list[int] = Field(
        default_factory=list,
        description="HTTP status codes exercised by matched tests.",
    )
    untested_status_codes: list[int] = Field(
        default_factory=list,
        description="Documented status codes with no test coverage.",
    )
    gaps: list[CoverageGap] = Field(
        default_factory=list,
        description="Identified coverage gaps and weaknesses.",
    )
    assertion_quality_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Quality score from 0.0 (untested) to 1.0 (strict schema assertions).",
    )
    critique_summary: str = Field(
        default="",
        description="Narrative critique of test quality, assertion depth, and recommendations.",
    )


class AuditReport(BaseModel):
    """Aggregated summary of an audit execution across an entire specification."""

    model_config = ConfigDict(extra="ignore")

    spec_source: str = Field(
        default="",
        description="Source specification path or identifier.",
    )
    artifact_source: str = Field(
        default="",
        description="Source test artifact path or identifier.",
    )
    total_spec_operations: int = Field(
        default=0,
        ge=0,
        description="Total count of operations defined in the specification.",
    )
    covered_operations: int = Field(
        default=0,
        ge=0,
        description="Total count of operations exercised by at least one test.",
    )
    operation_coverage_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Percentage of operations covered by test requests.",
    )
    total_documented_statuses: int = Field(
        default=0,
        ge=0,
        description="Total status codes documented across all operations.",
    )
    covered_documented_statuses: int = Field(
        default=0,
        ge=0,
        description="Documented status codes exercised by test requests.",
    )
    status_coverage_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Percentage of documented status codes covered.",
    )
    total_gaps: int = Field(
        default=0,
        ge=0,
        description="Total count of identified coverage gaps.",
    )
    gaps_by_severity: dict[str, int] = Field(
        default_factory=dict,
        description="Count of gaps grouped by severity rating.",
    )
    operation_critiques: list[OperationCritique] = Field(
        default_factory=list,
        description="Individual per-operation critique records.",
    )
