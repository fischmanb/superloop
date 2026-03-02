"""Tests for lease comp search and filtering (Feature #2).

Covers: LeaseComp data model, LeaseCompFilter, search_comps, load_comps_from_json,
        format_comps_table, and the CLI main() entrypoint.

Test ID prefix: LC
"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

from auto_sdd.lib.lease_comp_search import (
    LeaseComp,
    LeaseCompFilter,
    ValidationError,
    format_comps_table,
    load_comps_from_json,
    search_comps,
)
from auto_sdd.scripts.lease_comp_search import main as cli_main


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_comp(**overrides) -> LeaseComp:
    """Return a valid LeaseComp, optionally overriding specific fields."""
    defaults = {
        "id": "C001",
        "property_address": "350 Fifth Avenue",
        "market": "NYC",
        "submarket": "Midtown",
        "tenant": "Acme Corp",
        "landlord": "Empire State Realty",
        "execution_date": date(2024, 1, 15),
        "commencement_date": date(2024, 3, 1),
        "expiration_date": date(2034, 2, 28),
        "term_months": 120,
        "size_sf": 12500,
        "asking_rent_psf": 75.0,
        "effective_rent_psf": 68.0,
        "free_rent_months": 6,
        "lease_type": "Direct",
        "property_type": "Office",
        "floor": "15",
        "source": "CoStar",
    }
    defaults.update(overrides)
    return LeaseComp(**defaults)


def _make_comp_dict(**overrides) -> dict:
    """Return a valid comp dict, optionally overriding fields."""
    defaults = {
        "id": "C001",
        "property_address": "350 Fifth Avenue",
        "market": "NYC",
        "submarket": "Midtown",
        "tenant": "Acme Corp",
        "landlord": "Empire State Realty",
        "execution_date": "2024-01-15",
        "commencement_date": "2024-03-01",
        "expiration_date": "2034-02-28",
        "term_months": 120,
        "size_sf": 12500,
        "asking_rent_psf": 75.0,
        "effective_rent_psf": 68.0,
        "free_rent_months": 6,
        "lease_type": "Direct",
        "property_type": "Office",
        "floor": "15",
        "source": "CoStar",
    }
    defaults.update(overrides)
    return defaults


SAMPLE_COMPS_DATA = [
    {
        "id": "C001",
        "property_address": "350 Fifth Avenue",
        "market": "NYC",
        "submarket": "Midtown",
        "tenant": "Acme Corp",
        "landlord": "Empire State Realty",
        "execution_date": "2024-01-15",
        "commencement_date": "2024-03-01",
        "expiration_date": "2034-02-28",
        "term_months": 120,
        "size_sf": 12500,
        "asking_rent_psf": 75.0,
        "effective_rent_psf": 68.0,
        "free_rent_months": 6,
        "lease_type": "Direct",
        "property_type": "Office",
        "floor": "15",
        "source": "CoStar",
    },
    {
        "id": "C002",
        "property_address": "1 World Trade Center",
        "market": "NYC",
        "submarket": "Downtown",
        "tenant": "Beta Inc",
        "landlord": "Silverstein Properties",
        "execution_date": "2023-09-20",
        "commencement_date": "2024-01-01",
        "expiration_date": "2031-12-31",
        "term_months": 96,
        "size_sf": 8200,
        "asking_rent_psf": 68.5,
        "effective_rent_psf": 60.0,
        "free_rent_months": 9,
        "lease_type": "Direct",
        "property_type": "Office",
        "floor": "42",
        "source": "CoStar",
    },
    {
        "id": "C003",
        "property_address": "225 West Wacker Drive",
        "market": "Chicago",
        "submarket": "West Loop",
        "tenant": "Gamma LLC",
        "landlord": "Equity Commonwealth",
        "execution_date": "2023-06-01",
        "commencement_date": "2023-09-01",
        "expiration_date": "2033-08-31",
        "term_months": 120,
        "size_sf": 18000,
        "asking_rent_psf": 42.0,
        "effective_rent_psf": 38.0,
        "free_rent_months": 4,
        "lease_type": "Direct",
        "property_type": "Office",
        "floor": "10",
        "source": "CoStar",
    },
    {
        "id": "C004",
        "property_address": "100 N Michigan Ave",
        "market": "Chicago",
        "submarket": "Michigan Avenue",
        "tenant": "Retail Giant Inc",
        "landlord": "John Buck Company",
        "execution_date": "2022-11-30",
        "commencement_date": "2023-02-01",
        "expiration_date": "2028-01-31",
        "term_months": 60,
        "size_sf": 3500,
        "asking_rent_psf": 110.0,
        "effective_rent_psf": 98.0,
        "free_rent_months": 3,
        "lease_type": "Direct",
        "property_type": "Retail",
        "floor": "Ground",
        "source": "CoStar",
    },
    {
        "id": "C005",
        "property_address": "555 W 34th St",
        "market": "NYC",
        "submarket": "Hudson Yards",
        "tenant": "Amazon Inc",
        "landlord": "Related Companies",
        "execution_date": "2022-03-10",
        "commencement_date": "2022-07-01",
        "expiration_date": "2037-06-30",
        "term_months": 180,
        "size_sf": 335000,
        "asking_rent_psf": 85.0,
        "effective_rent_psf": 79.0,
        "free_rent_months": 18,
        "lease_type": "Direct",
        "property_type": "Office",
        "floor": "1-15",
        "source": "CoStar",
    },
]


# ---------------------------------------------------------------------------
# LC-001 — LC-004: LeaseComp data model
# ---------------------------------------------------------------------------

class TestLeaseCompFromDict:
    """LC-001 through LC-004: LeaseComp.from_dict construction and validation."""

    def test_lc001_from_dict_all_fields(self):
        """LC-001: Construct a LeaseComp from a complete valid dict."""
        d = _make_comp_dict()
        comp = LeaseComp.from_dict(d)
        assert comp.id == "C001"
        assert comp.property_address == "350 Fifth Avenue"
        assert comp.market == "NYC"
        assert comp.execution_date == date(2024, 1, 15)
        assert comp.size_sf == 12500
        assert comp.asking_rent_psf == 75.0

    def test_lc002_missing_required_field_raises_value_error(self):
        """LC-002: Missing required field raises ValueError."""
        d = _make_comp_dict()
        del d["size_sf"]
        with pytest.raises(ValueError, match="size_sf"):
            LeaseComp.from_dict(d)

    def test_lc003_negative_size_raises_validation_error(self):
        """LC-003: Negative size_sf raises ValidationError."""
        with pytest.raises(ValidationError, match="size_sf"):
            _make_comp(size_sf=-100)

    def test_lc004_negative_rent_raises_validation_error(self):
        """LC-004: Negative asking_rent_psf raises ValidationError."""
        with pytest.raises(ValidationError, match="asking_rent_psf"):
            _make_comp(asking_rent_psf=-5.0)

    def test_lc004b_zero_rent_is_valid(self):
        """Rent of 0 is allowed (free space / sublease scenarios)."""
        comp = _make_comp(asking_rent_psf=0.0, effective_rent_psf=0.0)
        assert comp.asking_rent_psf == 0.0

    def test_lc004c_date_string_parsed_correctly(self):
        """LC-004c: Date strings in YYYY-MM-DD format are parsed."""
        d = _make_comp_dict(execution_date="2023-06-15")
        comp = LeaseComp.from_dict(d)
        assert comp.execution_date == date(2023, 6, 15)

    def test_lc004d_missing_landlord_raises_value_error(self):
        """Missing landlord key raises ValueError."""
        d = _make_comp_dict()
        del d["landlord"]
        with pytest.raises(ValueError, match="landlord"):
            LeaseComp.from_dict(d)


# ---------------------------------------------------------------------------
# LC-005 — LC-017: search_comps filtering
# ---------------------------------------------------------------------------

class TestSearchCompsFiltering:
    """LC-005 through LC-017: search_comps filter logic."""

    def setup_method(self):
        self.comps = [LeaseComp.from_dict(d) for d in SAMPLE_COMPS_DATA]

    def test_lc005_filter_by_market(self):
        """LC-005: Filter by market returns only matching comps."""
        result = search_comps(self.comps, LeaseCompFilter(market="NYC"))
        assert all(c.market == "NYC" for c in result)
        assert len(result) == 3

    def test_lc006_filter_market_case_insensitive(self):
        """LC-006: Market filter is case-insensitive."""
        result_lower = search_comps(self.comps, LeaseCompFilter(market="nyc"))
        result_upper = search_comps(self.comps, LeaseCompFilter(market="NYC"))
        assert len(result_lower) == len(result_upper) == 3

    def test_lc007_filter_by_property_type(self):
        """LC-007: Filter by property_type returns only matching comps."""
        result = search_comps(self.comps, LeaseCompFilter(property_type="Retail"))
        assert len(result) == 1
        assert result[0].id == "C004"

    def test_lc008_filter_min_size(self):
        """LC-008: min_size_sf excludes comps below threshold."""
        result = search_comps(self.comps, LeaseCompFilter(min_size_sf=15000))
        assert all(c.size_sf >= 15000 for c in result)
        # C003 (18000) and C005 (335000)
        assert len(result) == 2

    def test_lc009_filter_max_size(self):
        """LC-009: max_size_sf excludes comps above threshold."""
        result = search_comps(self.comps, LeaseCompFilter(max_size_sf=5000))
        assert all(c.size_sf <= 5000 for c in result)
        # Only C004 (3500)
        assert len(result) == 1

    def test_lc010_filter_rent_range(self):
        """LC-010: Rent range filter returns only comps within [min, max]."""
        result = search_comps(
            self.comps, LeaseCompFilter(min_rent_psf=65.0, max_rent_psf=80.0)
        )
        assert all(65.0 <= c.asking_rent_psf <= 80.0 for c in result)
        # C001 (75.0), C002 (68.5)
        assert len(result) == 2

    def test_lc011_filter_execution_date_range(self):
        """LC-011: Date range returns comps executed within [after, before]."""
        result = search_comps(
            self.comps,
            LeaseCompFilter(
                executed_after=date(2023, 1, 1),
                executed_before=date(2023, 12, 31),
            ),
        )
        assert all(
            date(2023, 1, 1) <= c.execution_date <= date(2023, 12, 31)
            for c in result
        )
        # C002 (2023-09-20), C003 (2023-06-01)
        assert len(result) == 2

    def test_lc012_filter_tenant_contains(self):
        """LC-012: tenant_contains filter is case-insensitive substring match."""
        result = search_comps(self.comps, LeaseCompFilter(tenant_contains="amazon"))
        assert len(result) == 1
        assert result[0].tenant == "Amazon Inc"

    def test_lc013_combined_filters_and_logic(self):
        """LC-013: Multiple filters combine with AND semantics."""
        result = search_comps(
            self.comps,
            LeaseCompFilter(market="NYC", min_size_sf=10000),
        )
        # C001 (NYC, 12500) and C005 (NYC, 335000)
        assert len(result) == 2
        assert all(c.market == "NYC" and c.size_sf >= 10000 for c in result)

    def test_lc014_empty_filter_returns_all(self):
        """LC-014: Empty filter (no criteria) returns all comps."""
        result = search_comps(self.comps, LeaseCompFilter())
        assert len(result) == len(self.comps)

    def test_lc015_no_match_returns_empty_list(self):
        """LC-015: Filter matching no comps returns an empty list."""
        result = search_comps(self.comps, LeaseCompFilter(market="Boston"))
        assert result == []

    def test_lc016_results_sorted_by_date_descending(self):
        """LC-016: Results are sorted by execution_date newest first."""
        result = search_comps(self.comps, LeaseCompFilter())
        dates = [c.execution_date for c in result]
        assert dates == sorted(dates, reverse=True)

    def test_lc017_filter_by_lease_type(self):
        """LC-017: Filter by lease_type is case-insensitive."""
        result = search_comps(self.comps, LeaseCompFilter(lease_type="direct"))
        assert len(result) == 5  # all sample comps are Direct

    def test_lc017b_filter_submarket(self):
        """Filter by submarket."""
        result = search_comps(self.comps, LeaseCompFilter(submarket="Midtown"))
        assert len(result) == 1
        assert result[0].id == "C001"

    def test_lc017c_landlord_contains(self):
        """Filter by landlord name substring."""
        result = search_comps(self.comps, LeaseCompFilter(landlord_contains="silverstein"))
        assert len(result) == 1
        assert result[0].id == "C002"


# ---------------------------------------------------------------------------
# LC-018 — LC-021: load_comps_from_json
# ---------------------------------------------------------------------------

class TestLoadCompsFromJson:
    """LC-018 through LC-021: load_comps_from_json file loading."""

    def test_lc018_load_valid_json(self, tmp_path: Path):
        """LC-018: Valid JSON array loads all records."""
        f = tmp_path / "comps.json"
        f.write_text(json.dumps(SAMPLE_COMPS_DATA), encoding="utf-8")
        comps = load_comps_from_json(f)
        assert len(comps) == 5
        assert all(isinstance(c, LeaseComp) for c in comps)

    def test_lc019_empty_json_array(self, tmp_path: Path):
        """LC-019: Empty JSON array returns empty list."""
        f = tmp_path / "empty.json"
        f.write_text("[]", encoding="utf-8")
        comps = load_comps_from_json(f)
        assert comps == []

    def test_lc020_missing_file_raises(self):
        """LC-020: Non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_comps_from_json(Path("/tmp/does_not_exist_xyz.json"))

    def test_lc021_malformed_json_raises_value_error(self, tmp_path: Path):
        """LC-021: Invalid JSON raises ValueError."""
        f = tmp_path / "bad.json"
        f.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_comps_from_json(f)

    def test_lc021b_json_object_not_array_raises(self, tmp_path: Path):
        """Top-level JSON object (not array) raises ValueError."""
        f = tmp_path / "object.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        with pytest.raises(ValueError, match="JSON array"):
            load_comps_from_json(f)


# ---------------------------------------------------------------------------
# LC-022 — LC-024: format_comps_table
# ---------------------------------------------------------------------------

class TestFormatCompsTable:
    """LC-022 through LC-024: format_comps_table output formatting."""

    def test_lc022_empty_list_returns_no_match_message(self):
        """LC-022: Empty list returns a human-readable no-match message."""
        output = format_comps_table([])
        assert "No lease comps found" in output

    def test_lc023_table_contains_address_and_market(self):
        """LC-023: Table output contains comp address and market."""
        comp = _make_comp()
        output = format_comps_table([comp])
        assert "350 Fifth Avenue" in output
        assert "NYC" in output

    def test_lc024_table_shows_correct_match_count(self):
        """LC-024: Header shows correct number of matches."""
        comps = [_make_comp(id=f"C{i:03d}") for i in range(1, 4)]
        output = format_comps_table(comps)
        assert "3 matches" in output

    def test_lc024b_singular_match_count(self):
        """Single match says '1 match' (not '1 matches')."""
        output = format_comps_table([_make_comp()])
        assert "1 match" in output
        assert "1 matches" not in output


# ---------------------------------------------------------------------------
# LC-025 — LC-028: CLI main()
# ---------------------------------------------------------------------------

class TestCliMain:
    """LC-025 through LC-028: CLI entrypoint behaviour."""

    def test_lc025_cli_prints_filtered_comps(self, tmp_path: Path, capsys):
        """LC-025: CLI with --market filter prints only matching comps."""
        f = tmp_path / "comps.json"
        f.write_text(json.dumps(SAMPLE_COMPS_DATA), encoding="utf-8")
        rc = cli_main([str(f), "--market", "Chicago"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Chicago" in out
        # NYC comps should not appear
        assert "350 Fifth Avenue" not in out

    def test_lc026_cli_no_filters_prints_all(self, tmp_path: Path, capsys):
        """LC-026: CLI with no filters prints all comps."""
        f = tmp_path / "comps.json"
        f.write_text(json.dumps(SAMPLE_COMPS_DATA), encoding="utf-8")
        rc = cli_main([str(f)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "5 matches" in out

    def test_lc027_cli_exits_0_on_success(self, tmp_path: Path):
        """LC-027: CLI exits with code 0 for a valid request."""
        f = tmp_path / "comps.json"
        f.write_text(json.dumps(SAMPLE_COMPS_DATA), encoding="utf-8")
        rc = cli_main([str(f), "--market", "NYC"])
        assert rc == 0

    def test_lc028_cli_exits_nonzero_for_missing_file(self, capsys):
        """LC-028: CLI exits non-zero and prints error for missing file."""
        rc = cli_main(["/tmp/no_such_file_xyz.json"])
        assert rc != 0
        err = capsys.readouterr().err
        assert "error" in err.lower()

    def test_lc028b_cli_min_size_filter(self, tmp_path: Path, capsys):
        """CLI --min-size filter excludes small comps."""
        f = tmp_path / "comps.json"
        f.write_text(json.dumps(SAMPLE_COMPS_DATA), encoding="utf-8")
        rc = cli_main([str(f), "--min-size", "50000"])
        assert rc == 0
        out = capsys.readouterr().out
        # Only C005 (335000 sf)
        assert "Amazon Inc" in out
        assert "Acme Corp" not in out

    def test_lc028c_cli_combined_filters(self, tmp_path: Path, capsys):
        """CLI with multiple filters applies AND logic."""
        f = tmp_path / "comps.json"
        f.write_text(json.dumps(SAMPLE_COMPS_DATA), encoding="utf-8")
        rc = cli_main([str(f), "--market", "NYC", "--min-size", "10000"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "2 matches" in out

    def test_lc028d_cli_no_results_shows_no_match_message(self, tmp_path: Path, capsys):
        """CLI with filter matching nothing shows no-match message."""
        f = tmp_path / "comps.json"
        f.write_text(json.dumps(SAMPLE_COMPS_DATA), encoding="utf-8")
        rc = cli_main([str(f), "--market", "Boston"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "No lease comps found" in out

    def test_lc028e_cli_date_filter_after(self, tmp_path: Path, capsys):
        """CLI --after filter excludes comps before the date."""
        f = tmp_path / "comps.json"
        f.write_text(json.dumps(SAMPLE_COMPS_DATA), encoding="utf-8")
        rc = cli_main([str(f), "--after", "2024-01-01"])
        assert rc == 0
        out = capsys.readouterr().out
        # Only C001 (2024-01-15)
        assert "1 match" in out
