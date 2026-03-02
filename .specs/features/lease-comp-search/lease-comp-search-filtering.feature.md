---
feature: Lease comp search and filtering
domain: lease-comp-search
source: py/auto_sdd/lib/lease_comp_search.py, py/auto_sdd/scripts/lease_comp_search.py
tests:
  - py/tests/test_lease_comp_search.py
status: implemented
created: 2026-03-02
updated: 2026-03-02
---

# Lease Comp Search and Filtering

**Source Files**:
- `py/auto_sdd/lib/lease_comp_search.py` — LeaseComp dataclass, LeaseCompFilter, search logic
- `py/auto_sdd/scripts/lease_comp_search.py` — CLI entrypoint

## Feature: LeaseComp data model

### Scenario: Construct a LeaseComp from a dict
Given a dict with all required LeaseComp fields (address, market, size_sf, asking_rent_psf, execution_date, etc.)
When `LeaseComp.from_dict(d)` is called
Then a `LeaseComp` instance is returned with all fields populated

### Scenario: Missing required field raises ValueError
Given a dict missing the `size_sf` key
When `LeaseComp.from_dict(d)` is called
Then `ValueError` is raised identifying the missing field

### Scenario: Negative size raises ValidationError
Given a dict with `size_sf` set to -100
When `LeaseComp.from_dict(d)` is called
Then `ValidationError` is raised indicating size must be positive

### Scenario: Negative rent raises ValidationError
Given a dict with `asking_rent_psf` set to -5.0
When `LeaseComp.from_dict(d)` is called
Then `ValidationError` is raised indicating rent must be non-negative

## Feature: Lease comp filtering

### Scenario: Filter by market returns only matching comps
Given a list of comps with markets "NYC", "Chicago", and "LA"
And a `LeaseCompFilter(market="NYC")`
When `search_comps(comps, filter)` is called
Then only comps with market "NYC" are returned

### Scenario: Filter is case-insensitive for market
Given comps with market "nyc" and "NYC"
And a filter with market="nyc"
When `search_comps(comps, filter)` is called
Then both comps are returned

### Scenario: Filter by property type
Given comps with property_type "Office" and "Retail"
And a filter with property_type="Office"
When `search_comps(comps, filter)` is called
Then only "Office" comps are returned

### Scenario: Filter by minimum size
Given comps with size_sf 2000, 5000, and 10000
And a filter with min_size_sf=5000
When `search_comps(comps, filter)` is called
Then comps with 5000 and 10000 sf are returned; 2000 sf is excluded

### Scenario: Filter by maximum size
Given comps with size_sf 2000, 5000, and 10000
And a filter with max_size_sf=5000
When `search_comps(comps, filter)` is called
Then comps with 2000 and 5000 sf are returned; 10000 sf is excluded

### Scenario: Filter by rent range
Given comps with asking_rent_psf 30.0, 55.0, and 80.0
And a filter with min_rent_psf=40.0 and max_rent_psf=70.0
When `search_comps(comps, filter)` is called
Then only the 55.0 comp is returned

### Scenario: Filter by execution date range
Given comps executed on 2022-01-15, 2023-06-01, and 2024-03-10
And a filter with executed_after=2023-01-01 and executed_before=2024-01-01
When `search_comps(comps, filter)` is called
Then only the 2023-06-01 comp is returned

### Scenario: Filter by tenant name substring (case-insensitive)
Given comps with tenants "Google LLC", "Amazon Inc", and "Apple Corp"
And a filter with tenant_contains="amazon"
When `search_comps(comps, filter)` is called
Then only the Amazon comp is returned

### Scenario: Multiple filters are combined with AND logic
Given comps in "NYC" with sizes 2000 and 8000 sf, and a Chicago comp with 8000 sf
And a filter with market="NYC" and min_size_sf=5000
When `search_comps(comps, filter)` is called
Then only the NYC 8000 sf comp is returned

### Scenario: Empty filter returns all comps
Given a list of 5 comps
And a `LeaseCompFilter()` with no fields set
When `search_comps(comps, filter)` is called
Then all 5 comps are returned

### Scenario: Filter matching nothing returns empty list
Given a list of NYC comps
And a filter with market="Boston"
When `search_comps(comps, filter)` is called
Then an empty list is returned

### Scenario: Results are sorted by execution_date descending
Given comps executed on 2022-01-15, 2024-03-10, and 2023-06-01
And an empty filter
When `search_comps(comps, filter)` is called
Then results are returned with 2024-03-10 first, then 2023-06-01, then 2022-01-15

## Feature: JSON loading

### Scenario: Load comps from a JSON file
Given a JSON file containing an array of lease comp records
When `load_comps_from_json(path)` is called
Then a list of `LeaseComp` instances is returned

### Scenario: Empty JSON file returns empty list
Given a JSON file containing an empty array `[]`
When `load_comps_from_json(path)` is called
Then an empty list is returned

### Scenario: Missing file raises FileNotFoundError
Given a path to a JSON file that does not exist
When `load_comps_from_json(path)` is called
Then `FileNotFoundError` is raised

### Scenario: Malformed JSON raises ValueError
Given a JSON file with invalid JSON syntax
When `load_comps_from_json(path)` is called
Then `ValueError` is raised indicating the file is not valid JSON

## Feature: CLI entrypoint

### Scenario: CLI prints filtered comps as table
Given a JSON comps file with 3 lease comps
And the CLI is invoked with `--market NYC`
When the CLI runs
Then only NYC comps are printed in a tabular format

### Scenario: CLI with no filters prints all comps
Given a JSON comps file with 5 comps
When the CLI is invoked with only the file path (no filters)
Then all 5 comps are printed

### Scenario: CLI exits 0 on success
Given a valid JSON comps file
When the CLI is invoked with valid arguments
Then the process exits with code 0

### Scenario: CLI exits non-zero for missing file
Given a path to a JSON file that does not exist
When the CLI is invoked with that path
Then the process exits with a non-zero code and prints an error message

## UI Mockup (CLI output)

```
$ python -m auto_sdd.scripts.lease_comp_search comps.json --market NYC --min-size 5000

Lease Comp Search Results (3 matches)
======================================
  Address                     Market  Submarket     Tenant          Size(SF)  Asking($/SF)  Execution
  ---------------------------  ------  ------------  --------------  --------  ------------  ----------
  350 Fifth Avenue             NYC     Midtown       Acme Corp       12,500    $75.00        2024-01-15
  1 World Trade Center         NYC     Downtown      Beta Inc         8,200    $68.50        2023-09-20
  30 Rockefeller Plaza         NYC     Midtown       Gamma Ltd        6,000    $72.00        2023-03-01
```

## Learnings

- LeaseComp filtering uses AND semantics — every set filter must match.
- Case-insensitive matching on string fields (market, property_type, tenant, landlord) improves usability.
- Results are always returned sorted newest-first (execution_date descending).
