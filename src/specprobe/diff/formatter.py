"""Output formatting utilities for specprobe diff (streaming JSONL and Rich summary table)."""

import json
from collections.abc import Generator, Iterable

from rich.console import Console
from rich.table import Table

from specprobe.diff.models import DiffChangeRecord, DiffSummary


def stream_diff_as_jsonl(records: Iterable[DiffChangeRecord]) -> Generator[str, None, None]:
    """Serialize DiffChangeRecord sequence to line-delimited JSON (JSONL) strings."""
    for record in records:
        yield json.dumps(record.model_dump(mode="json")) + "\n"


def render_diff_summary(summary: DiffSummary, console: Console | None = None) -> None:
    """Render a formatted human-readable summary table of structural differences to stderr."""
    target_console = console or Console(stderr=True)
    table = Table(title="SpecProbe Specification Diff Summary")
    table.add_column("Category", style="cyan")
    table.add_column("Count", style="green")

    table.add_row("Total Changes", str(summary.total_changes))
    table.add_row("Breaking Changes", str(summary.breaking_changes))
    table.add_row("Operations Added", str(summary.operations_added))
    table.add_row("Operations Removed", str(summary.operations_removed))
    table.add_row("Schema/Status Breaking Changes", str(summary.schema_breaking_changes))

    target_console.print(table)
