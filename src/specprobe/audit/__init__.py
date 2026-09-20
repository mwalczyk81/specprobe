"""Audit package for evaluating API test artifacts against OpenAPI specifications."""

__all__ = [
    "ArtifactTestItem",
    "AuditEngine",
    "AuditReport",
    "CoverageGap",
    "CoverageGapSeverity",
    "CoverageGapType",
    "OperationCritique",
]


def __getattr__(name: str):
    """Lazy import audit components to avoid circular import issues."""
    if name in {
        "ArtifactTestItem",
        "AuditReport",
        "CoverageGap",
        "CoverageGapSeverity",
        "CoverageGapType",
        "OperationCritique",
    }:
        from specprobe.audit import models

        return getattr(models, name)
    if name == "AuditEngine":
        from specprobe.audit.engine import AuditEngine

        return AuditEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
