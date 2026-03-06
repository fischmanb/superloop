"""Campaign Intelligence System — Runtime Attribution.

Joins auto-QA failures back to feature vectors via file path intersection.
Reads failure catalog (Phase 4a), RCA report (Phase 4b), and fix report
(Phase 5) from the validation log directory, then writes runtime_signals_v1
to matching feature vectors.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from auto_sdd.lib.vector_store import FeatureVector, VectorStore

logger = logging.getLogger(__name__)


def _read_json(path: Path) -> Any:
    """Read a JSON file and return its contents, or None if missing."""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _build_file_feature_map(
    vectors: list[FeatureVector],
) -> dict[str, list[str]]:
    """Map file paths to feature vector IDs.

    For each vector with build_signals_v1.files_touched, maps every
    file path to a list of vector IDs that touched it.

    Returns:
        Dict mapping file path -> list of "{campaign_id}-{feature_id}" IDs.
    """
    file_map: dict[str, list[str]] = {}
    for vec in vectors:
        build_signals = vec.sections.get("build_signals_v1")
        if not isinstance(build_signals, dict):
            continue
        files_touched = build_signals.get("files_touched")
        if not isinstance(files_touched, list):
            continue
        vid = f"{vec.campaign_id}-{vec.feature_id}"
        for fpath in files_touched:
            if isinstance(fpath, str) and fpath:
                file_map.setdefault(fpath, []).append(vid)
    return file_map


def _find_fix_result(
    fix_report: list[dict[str, Any]] | None,
    root_cause_id: str,
) -> tuple[bool, bool]:
    """Look up fix results for a root cause ID.

    Returns:
        (fix_attempted, fix_succeeded) tuple.
    """
    if not fix_report:
        return False, False
    for fix in fix_report:
        if fix.get("root_cause_id") == root_cause_id:
            status = fix.get("status", "")
            return True, status == "FIX_VERIFIED"
    return False, False


def backfill_runtime_signals(
    vector_store: VectorStore,
    campaign_id: str,
    validation_log_dir: Path,
) -> dict[str, Any]:
    """Join auto-QA failures to feature vectors via file path intersection.

    Reads Phase 4a failure catalog, Phase 4b RCA report, and Phase 5 fix
    report (if present). For each root cause, intersects likely_files with
    each feature's files_touched to attribute failures. Writes
    runtime_signals_v1 to all campaign vectors.

    Args:
        vector_store: The feature vector store instance.
        campaign_id: Campaign to backfill.
        validation_log_dir: Root of validation log output
            (contains phase-4a/, phase-4b/, phase-5/ subdirs).

    Returns:
        Summary dict with counts of attributed features and failures.
    """
    # Read Phase 4a failure catalog
    catalog_path = validation_log_dir / "phase-4a" / "failure-catalog.v1.json"
    catalog_data = _read_json(catalog_path)
    failure_catalog: list[dict[str, Any]] = []
    if isinstance(catalog_data, dict):
        failure_catalog = catalog_data.get("catalog", [])
    elif isinstance(catalog_data, list):
        failure_catalog = catalog_data

    # Read Phase 4b RCA report
    rca_path = validation_log_dir / "phase-4b" / "rca-report.v1.json"
    rca_data = _read_json(rca_path)
    root_causes: list[dict[str, Any]] = []
    if isinstance(rca_data, dict):
        root_causes = rca_data.get("root_causes", [])
    elif isinstance(rca_data, list):
        root_causes = rca_data

    # Read Phase 5 fix report (optional)
    fix_path = validation_log_dir / "phase-5" / "fix-report.v1.json"
    fix_data = _read_json(fix_path)
    fix_results: list[dict[str, Any]] | None = None
    if isinstance(fix_data, dict):
        fix_results = fix_data.get("fix_results", [])
    elif isinstance(fix_data, list):
        fix_results = fix_data

    # Query all vectors for this campaign
    vectors = vector_store.query_vectors({"campaign_id": campaign_id})
    if not vectors:
        logger.warning(
            "No vectors found for campaign %s — skipping backfill",
            campaign_id,
        )
        return {
            "features_attributed": 0,
            "failures_attributed": 0,
            "unattributed_failures": 0,
            "cross_feature_interactions": 0,
        }

    # Build file→feature map
    file_feature_map = _build_file_feature_map(vectors)

    # Track per-vector attribution
    vector_id_to_runtime: dict[str, dict[str, Any]] = {}
    for vec in vectors:
        vid = f"{vec.campaign_id}-{vec.feature_id}"
        vector_id_to_runtime[vid] = {
            "runtime_failures_caused": 0,
            "failure_types": [],
            "rca_root_causes": [],
            "fix_attempted": False,
            "fix_succeeded": False,
            "cross_feature_interaction": False,
        }

    # Attribution counters
    failures_attributed = 0
    unattributed_failures = 0
    cross_feature_interactions = 0

    # For each root cause, intersect likely_files with file→feature map
    for rc in root_causes:
        rc_id = rc.get("id", rc.get("root_cause_id", "unknown"))
        likely_files = rc.get("likely_files", [])
        failure_type = rc.get("category", rc.get("type", "unknown"))

        if not isinstance(likely_files, list):
            likely_files = []

        # Find all vector IDs implicated
        implicated_vids: set[str] = set()
        for fpath in likely_files:
            if isinstance(fpath, str) and fpath in file_feature_map:
                implicated_vids.update(file_feature_map[fpath])

        if not implicated_vids:
            logger.debug(
                "Root cause %s: likely_files %s do not match any feature",
                rc_id,
                likely_files,
            )
            unattributed_failures += 1
            continue

        # Check if cross-feature interaction
        is_cross = len(implicated_vids) > 1
        if is_cross:
            cross_feature_interactions += 1

        # Look up fix result for this root cause
        fix_attempted, fix_succeeded = _find_fix_result(fix_results, rc_id)

        failures_attributed += 1
        for vid in implicated_vids:
            if vid not in vector_id_to_runtime:
                continue
            rt = vector_id_to_runtime[vid]
            rt["runtime_failures_caused"] += 1
            if failure_type not in rt["failure_types"]:
                rt["failure_types"].append(failure_type)
            if rc_id not in rt["rca_root_causes"]:
                rt["rca_root_causes"].append(rc_id)
            if fix_attempted:
                rt["fix_attempted"] = True
            if fix_succeeded:
                rt["fix_succeeded"] = True
            if is_cross:
                rt["cross_feature_interaction"] = True

    # Compute ac_pass_rate per feature from failure catalog
    # Best effort: count passed vs failed criteria
    total_criteria = len(failure_catalog)
    passed_criteria = sum(
        1 for entry in failure_catalog
        if entry.get("status") == "passed"
        or entry.get("result") == "passed"
    )

    # Write runtime_signals_v1 to all vectors
    features_attributed = 0
    for vec in vectors:
        vid = f"{vec.campaign_id}-{vec.feature_id}"
        rt = vector_id_to_runtime.get(vid)
        if rt is None:
            continue

        # Compute per-feature ac_pass_rate (global rate as best effort)
        ac_pass_rate = 0.0
        if total_criteria > 0:
            ac_pass_rate = round(passed_criteria / total_criteria, 4)

        rt["ac_pass_rate"] = ac_pass_rate

        try:
            vector_store.update_section(vid, "runtime_signals_v1", rt)
            features_attributed += 1
        except KeyError:
            logger.debug("Could not update vector %s", vid)

    summary: dict[str, Any] = {
        "features_attributed": features_attributed,
        "failures_attributed": failures_attributed,
        "unattributed_failures": unattributed_failures,
        "cross_feature_interactions": cross_feature_interactions,
    }
    logger.info("Runtime attribution complete: %s", summary)
    return summary
