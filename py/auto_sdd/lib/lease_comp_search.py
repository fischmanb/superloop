"""
Lease comp search and filtering library.

Provides data structures and filtering logic for commercial real estate
lease comparable (comp) records.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional


class ValidationError(ValueError):
    """Raised when a LeaseComp field fails domain validation."""


@dataclass
class LeaseComp:
    """A single commercial real estate lease comparable record."""

    id: str
    property_address: str
    market: str
    submarket: str
    tenant: str
    landlord: str
    execution_date: date
    commencement_date: date
    expiration_date: date
    term_months: int
    size_sf: int
    asking_rent_psf: float
    effective_rent_psf: float
    free_rent_months: int
    lease_type: str       # e.g. "Direct", "Sublease"
    property_type: str    # e.g. "Office", "Retail", "Industrial"
    floor: str
    source: str

    def __post_init__(self) -> None:
        if self.size_sf <= 0:
            raise ValidationError(
                f"size_sf must be positive, got {self.size_sf}"
            )
        if self.asking_rent_psf < 0:
            raise ValidationError(
                f"asking_rent_psf must be non-negative, got {self.asking_rent_psf}"
            )
        if self.effective_rent_psf < 0:
            raise ValidationError(
                f"effective_rent_psf must be non-negative, got {self.effective_rent_psf}"
            )

    @classmethod
    def from_dict(cls, d: dict) -> "LeaseComp":
        """Construct a LeaseComp from a plain dict.

        Raises:
            ValueError: if a required key is missing.
            ValidationError: if a field value fails domain validation.
        """
        required_keys = [
            "id", "property_address", "market", "submarket",
            "tenant", "landlord", "execution_date", "commencement_date",
            "expiration_date", "term_months", "size_sf", "asking_rent_psf",
            "effective_rent_psf", "free_rent_months", "lease_type",
            "property_type", "floor", "source",
        ]
        for key in required_keys:
            if key not in d:
                raise ValueError(f"Missing required field: '{key}'")

        def _parse_date(v: object) -> date:
            if isinstance(v, date):
                return v
            if isinstance(v, str):
                return datetime.strptime(v, "%Y-%m-%d").date()
            raise ValueError(f"Cannot parse date from {v!r}")

        return cls(
            id=str(d["id"]),
            property_address=str(d["property_address"]),
            market=str(d["market"]),
            submarket=str(d["submarket"]),
            tenant=str(d["tenant"]),
            landlord=str(d["landlord"]),
            execution_date=_parse_date(d["execution_date"]),
            commencement_date=_parse_date(d["commencement_date"]),
            expiration_date=_parse_date(d["expiration_date"]),
            term_months=int(d["term_months"]),
            size_sf=int(d["size_sf"]),
            asking_rent_psf=float(d["asking_rent_psf"]),
            effective_rent_psf=float(d["effective_rent_psf"]),
            free_rent_months=int(d["free_rent_months"]),
            lease_type=str(d["lease_type"]),
            property_type=str(d["property_type"]),
            floor=str(d["floor"]),
            source=str(d["source"]),
        )


@dataclass
class LeaseCompFilter:
    """Criteria for filtering a list of LeaseComp records.

    All fields are optional. A filter with no fields set returns all comps.
    Multiple set fields are combined with AND semantics.
    String comparisons are case-insensitive.
    """

    market: Optional[str] = None
    submarket: Optional[str] = None
    property_type: Optional[str] = None
    lease_type: Optional[str] = None
    min_size_sf: Optional[int] = None
    max_size_sf: Optional[int] = None
    min_rent_psf: Optional[float] = None
    max_rent_psf: Optional[float] = None
    executed_after: Optional[date] = None
    executed_before: Optional[date] = None
    tenant_contains: Optional[str] = None
    landlord_contains: Optional[str] = None


def search_comps(
    comps: list[LeaseComp],
    filters: LeaseCompFilter,
) -> list[LeaseComp]:
    """Filter and sort a list of LeaseComp records.

    All active filter criteria are combined with AND semantics.
    String matching is case-insensitive.
    Results are returned sorted by execution_date descending (newest first).

    Args:
        comps: Source list of LeaseComp records.
        filters: Criteria to apply. Fields set to None are ignored.

    Returns:
        Filtered and sorted list of LeaseComp records.
    """
    results: list[LeaseComp] = []

    for comp in comps:
        if filters.market is not None:
            if comp.market.lower() != filters.market.lower():
                continue

        if filters.submarket is not None:
            if comp.submarket.lower() != filters.submarket.lower():
                continue

        if filters.property_type is not None:
            if comp.property_type.lower() != filters.property_type.lower():
                continue

        if filters.lease_type is not None:
            if comp.lease_type.lower() != filters.lease_type.lower():
                continue

        if filters.min_size_sf is not None:
            if comp.size_sf < filters.min_size_sf:
                continue

        if filters.max_size_sf is not None:
            if comp.size_sf > filters.max_size_sf:
                continue

        if filters.min_rent_psf is not None:
            if comp.asking_rent_psf < filters.min_rent_psf:
                continue

        if filters.max_rent_psf is not None:
            if comp.asking_rent_psf > filters.max_rent_psf:
                continue

        if filters.executed_after is not None:
            if comp.execution_date < filters.executed_after:
                continue

        if filters.executed_before is not None:
            if comp.execution_date > filters.executed_before:
                continue

        if filters.tenant_contains is not None:
            if filters.tenant_contains.lower() not in comp.tenant.lower():
                continue

        if filters.landlord_contains is not None:
            if filters.landlord_contains.lower() not in comp.landlord.lower():
                continue

        results.append(comp)

    results.sort(key=lambda c: c.execution_date, reverse=True)
    return results


def load_comps_from_json(path: Path) -> list[LeaseComp]:
    """Load lease comps from a JSON file.

    The file must contain a JSON array where each element is an object
    with all required LeaseComp fields.

    Args:
        path: Path to the JSON file.

    Returns:
        List of LeaseComp instances.

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: if the file is not valid JSON or contains invalid records.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Comps file not found: {path}")

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError(
            f"Expected a JSON array at top level, got {type(data).__name__}"
        )

    return [LeaseComp.from_dict(record) for record in data]


def format_comps_table(comps: list[LeaseComp]) -> str:
    """Format a list of comps as a plain-text table for CLI output.

    Returns an empty string if comps is empty.
    """
    if not comps:
        return "No lease comps found matching the given criteria."

    header = (
        f"{'Address':<40} {'Market':<8} {'Submarket':<14} "
        f"{'Tenant':<20} {'Size(SF)':>10} {'Asking($/SF)':>13} {'Execution':<12}"
    )
    separator = "-" * len(header)
    lines = [
        f"Lease Comp Search Results ({len(comps)} match{'es' if len(comps) != 1 else ''})",
        "=" * len(header),
        header,
        separator,
    ]
    for c in comps:
        lines.append(
            f"{c.property_address:<40} {c.market:<8} {c.submarket:<14} "
            f"{c.tenant:<20} {c.size_sf:>10,} {c.asking_rent_psf:>12.2f} "
            f"{c.execution_date.isoformat():<12}"
        )
    return "\n".join(lines)
