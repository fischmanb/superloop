"""
CLI entrypoint for lease comp search and filtering.

Usage:
    python -m auto_sdd.scripts.lease_comp_search <comps.json> [options]

Options:
    --market TEXT           Filter by market (case-insensitive)
    --submarket TEXT        Filter by submarket (case-insensitive)
    --property-type TEXT    Filter by property type (e.g., Office, Retail)
    --lease-type TEXT       Filter by lease type (e.g., Direct, Sublease)
    --min-size INT          Minimum size in square feet
    --max-size INT          Maximum size in square feet
    --min-rent FLOAT        Minimum asking rent ($/SF/year)
    --max-rent FLOAT        Maximum asking rent ($/SF/year)
    --after DATE            Only comps executed on or after this date (YYYY-MM-DD)
    --before DATE           Only comps executed on or before this date (YYYY-MM-DD)
    --tenant TEXT           Filter by tenant name substring
    --landlord TEXT         Filter by landlord name substring
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from auto_sdd.lib.lease_comp_search import (
    LeaseCompFilter,
    format_comps_table,
    load_comps_from_json,
    search_comps,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="lease_comp_search",
        description="Search and filter commercial real estate lease comps from a JSON file.",
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Path to JSON file containing lease comp records.",
    )
    parser.add_argument("--market", default=None, help="Filter by market (e.g., NYC)")
    parser.add_argument("--submarket", default=None, help="Filter by submarket")
    parser.add_argument(
        "--property-type", dest="property_type", default=None,
        help="Filter by property type (e.g., Office, Retail, Industrial)",
    )
    parser.add_argument(
        "--lease-type", dest="lease_type", default=None,
        help="Filter by lease type (e.g., Direct, Sublease)",
    )
    parser.add_argument(
        "--min-size", dest="min_size", type=int, default=None,
        help="Minimum size in square feet (inclusive)",
    )
    parser.add_argument(
        "--max-size", dest="max_size", type=int, default=None,
        help="Maximum size in square feet (inclusive)",
    )
    parser.add_argument(
        "--min-rent", dest="min_rent", type=float, default=None,
        help="Minimum asking rent in $/SF/year (inclusive)",
    )
    parser.add_argument(
        "--max-rent", dest="max_rent", type=float, default=None,
        help="Maximum asking rent in $/SF/year (inclusive)",
    )
    parser.add_argument(
        "--after", default=None,
        help="Only comps executed on or after this date (YYYY-MM-DD, inclusive)",
    )
    parser.add_argument(
        "--before", default=None,
        help="Only comps executed on or before this date (YYYY-MM-DD, inclusive)",
    )
    parser.add_argument(
        "--tenant", default=None,
        help="Filter by tenant name substring (case-insensitive)",
    )
    parser.add_argument(
        "--landlord", default=None,
        help="Filter by landlord name substring (case-insensitive)",
    )
    return parser.parse_args(argv)


def _parse_date_arg(value: str | None, flag: str) -> "datetime.date | None":
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit(f"error: invalid date for {flag}: {value!r} (expected YYYY-MM-DD)")


def main(argv: list[str] | None = None) -> int:
    """Run the lease comp search CLI.

    Returns:
        Exit code (0 = success, non-zero = error).
    """
    args = _parse_args(argv)

    after = _parse_date_arg(args.after, "--after")
    before = _parse_date_arg(args.before, "--before")

    try:
        comps = load_comps_from_json(args.file)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    filters = LeaseCompFilter(
        market=args.market,
        submarket=args.submarket,
        property_type=args.property_type,
        lease_type=args.lease_type,
        min_size_sf=args.min_size,
        max_size_sf=args.max_size,
        min_rent_psf=args.min_rent,
        max_rent_psf=args.max_rent,
        executed_after=after,
        executed_before=before,
        tenant_contains=args.tenant,
        landlord_contains=args.landlord,
    )

    results = search_comps(comps, filters)
    print(format_comps_table(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
