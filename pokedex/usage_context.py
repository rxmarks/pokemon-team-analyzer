"""Interpret recorded usage metadata without inventing freshness dates."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UsageContext:
    dataset_id: str | None
    month: str | None
    weighting_baseline: int | None
    source_url: str | None


def usage_context(
    format_value: str | None,
    month_value: str | None,
) -> UsageContext:
    """Validate recorded identifiers and derive the cache builder's source URL."""
    dataset_id = (format_value or "").strip()
    month = (month_value or "").strip()

    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", dataset_id):
        dataset_id = ""

    if not re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", month):
        month = ""

    baseline: int | None = None

    if dataset_id:
        prefix, separator, suffix = dataset_id.rpartition("-")
        if separator and prefix and suffix.isdigit():
            baseline = int(suffix)

    source_url = None

    if dataset_id and month:
        source_url = f"https://www.smogon.com/stats/{month}/{dataset_id}.txt.gz"

    return UsageContext(
        dataset_id=dataset_id or None,
        month=month or None,
        weighting_baseline=baseline,
        source_url=source_url,
    )
