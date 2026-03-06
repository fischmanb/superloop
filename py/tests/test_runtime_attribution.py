"""Tests for auto_sdd.lib.runtime_attribution — CIS Round 4."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from auto_sdd.lib.runtime_attribution import backfill_runtime_signals
from auto_sdd.lib.vector_store import FeatureVector, VectorStore


# ── Fixtures ──────────────────────────────────────────────────────────────


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _make_store(tmp_path: Path) -> VectorStore:
    """Create a VectorStore with 3 feature vectors."""
    store_path = tmp_path / "vectors.jsonl"
    store = VectorStore(store_path)

    for i, (name, files) in enumerate([
        ("auth-login", ["src/auth/login.ts", "src/auth/middleware.ts"]),
        ("dashboard", ["src/pages/dashboard.tsx", "src/components/chart.tsx"]),
        ("settings", ["src/pages/settings.tsx", "src/auth/middleware.ts"]),
    ]):
        vid = store.create_vector({
            "feature_id": i + 1,
            "feature_name": name,
            "campaign_id": "camp-001",
            "build_order_position": i + 1,
            "timestamp": "2026-03-06T00:00:00Z",
        })
        store.update_section(vid, "build_signals_v1", {
            "build_success": True,
            "files_touched": files,
        })

    return store


def _make_failure_catalog() -> dict[str, Any]:
    return {
        "catalog": [
            {"id": "fc-1", "status": "failed", "criterion": "login works"},
            {"id": "fc-2", "status": "failed", "criterion": "chart renders"},
            {"id": "fc-3", "status": "passed", "criterion": "page loads"},
        ],
        "stats": {"total": 3, "passed": 1, "failed": 2},
    }


def _make_rca_report() -> dict[str, Any]:
    return {
        "root_causes": [
            {
                "id": "rc-1",
                "category": "auth_error",
                "likely_files": ["src/auth/login.ts"],
                "description": "Login handler throws on invalid token",
            },
            {
                "id": "rc-2",
                "category": "render_error",
                "likely_files": [
                    "src/pages/dashboard.tsx",
                    "src/auth/middleware.ts",
                ],
                "description": "Dashboard fails when auth middleware blocks",
            },
        ],
    }


def _make_fix_report() -> dict[str, Any]:
    return {
        "fix_results": [
            {
                "root_cause_id": "rc-1",
                "status": "FIX_VERIFIED",
                "files_modified": ["src/auth/login.ts"],
            },
            {
                "root_cause_id": "rc-2",
                "status": "FIX_FAILED",
                "files_modified": [],
            },
        ],
    }


# ── Happy path ────────────────────────────────────────────────────────────


class TestBackfillRuntimeSignals:
    def test_happy_path_attributes_failures_to_correct_features(
        self, tmp_path: Path
    ) -> None:
        store = _make_store(tmp_path)
        log_dir = tmp_path / "logs"
        _write_json(log_dir / "phase-4a" / "failure-catalog.v1.json",
                     _make_failure_catalog())
        _write_json(log_dir / "phase-4b" / "rca-report.v1.json",
                     _make_rca_report())
        _write_json(log_dir / "phase-5" / "fix-report.v1.json",
                     _make_fix_report())

        summary = backfill_runtime_signals(store, "camp-001", log_dir)

        assert summary["features_attributed"] == 3
        assert summary["failures_attributed"] == 2

        # auth-login: rc-1 (login.ts) + rc-2 (middleware.ts shared)
        auth_vec = store.get_vector("camp-001-1")
        assert auth_vec is not None
        rt = auth_vec.sections["runtime_signals_v1"]
        assert rt["runtime_failures_caused"] == 2
        assert "auth_error" in rt["failure_types"]
        assert "render_error" in rt["failure_types"]
        assert rt["fix_attempted"] is True
        assert rt["fix_succeeded"] is True  # rc-1 was verified

        # dashboard: rc-2 (dashboard.tsx)
        dash_vec = store.get_vector("camp-001-2")
        assert dash_vec is not None
        rt2 = dash_vec.sections["runtime_signals_v1"]
        assert rt2["runtime_failures_caused"] == 1
        assert "render_error" in rt2["failure_types"]

    def test_cross_feature_interaction_detected(
        self, tmp_path: Path
    ) -> None:
        store = _make_store(tmp_path)
        log_dir = tmp_path / "logs"
        _write_json(log_dir / "phase-4a" / "failure-catalog.v1.json",
                     _make_failure_catalog())
        # rc-2 has likely_files that map to dashboard AND auth-login/settings
        _write_json(log_dir / "phase-4b" / "rca-report.v1.json",
                     _make_rca_report())

        summary = backfill_runtime_signals(store, "camp-001", log_dir)
        assert summary["cross_feature_interactions"] >= 1

        # Check cross_feature_interaction flag on implicated vectors
        # rc-2 likely_files: dashboard.tsx -> dashboard, middleware.ts -> auth + settings
        dash_vec = store.get_vector("camp-001-2")
        assert dash_vec is not None
        assert dash_vec.sections["runtime_signals_v1"]["cross_feature_interaction"] is True

    def test_unattributed_failures_counted(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        log_dir = tmp_path / "logs"
        _write_json(log_dir / "phase-4a" / "failure-catalog.v1.json",
                     _make_failure_catalog())
        _write_json(log_dir / "phase-4b" / "rca-report.v1.json", {
            "root_causes": [{
                "id": "rc-x",
                "category": "unknown",
                "likely_files": ["nonexistent/file.ts"],
            }],
        })

        summary = backfill_runtime_signals(store, "camp-001", log_dir)
        assert summary["unattributed_failures"] == 1

    def test_features_with_no_failures_get_zero(
        self, tmp_path: Path
    ) -> None:
        store = _make_store(tmp_path)
        log_dir = tmp_path / "logs"
        _write_json(log_dir / "phase-4a" / "failure-catalog.v1.json",
                     {"catalog": []})
        _write_json(log_dir / "phase-4b" / "rca-report.v1.json",
                     {"root_causes": []})

        summary = backfill_runtime_signals(store, "camp-001", log_dir)

        for i in range(1, 4):
            vec = store.get_vector(f"camp-001-{i}")
            assert vec is not None
            rt = vec.sections["runtime_signals_v1"]
            assert rt["runtime_failures_caused"] == 0

    def test_missing_phase5_handled_gracefully(
        self, tmp_path: Path
    ) -> None:
        store = _make_store(tmp_path)
        log_dir = tmp_path / "logs"
        _write_json(log_dir / "phase-4a" / "failure-catalog.v1.json",
                     _make_failure_catalog())
        _write_json(log_dir / "phase-4b" / "rca-report.v1.json",
                     _make_rca_report())
        # No Phase 5 fix report

        summary = backfill_runtime_signals(store, "camp-001", log_dir)
        assert summary["features_attributed"] == 3

        # fix_attempted should be False since no fix report
        auth_vec = store.get_vector("camp-001-1")
        assert auth_vec is not None
        rt = auth_vec.sections["runtime_signals_v1"]
        assert rt["fix_attempted"] is False
        assert rt["fix_succeeded"] is False

    def test_empty_failure_catalog_handled(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        log_dir = tmp_path / "logs"
        _write_json(log_dir / "phase-4a" / "failure-catalog.v1.json", {
            "catalog": [
                {"id": "fc-1", "status": "passed", "criterion": "all good"},
            ],
        })
        _write_json(log_dir / "phase-4b" / "rca-report.v1.json",
                     {"root_causes": []})

        summary = backfill_runtime_signals(store, "camp-001", log_dir)
        assert summary["failures_attributed"] == 0
        assert summary["features_attributed"] == 3

        # ac_pass_rate should be 1.0 (all passed)
        vec = store.get_vector("camp-001-1")
        assert vec is not None
        assert vec.sections["runtime_signals_v1"]["ac_pass_rate"] == 1.0

    def test_vectors_without_files_touched_skipped(
        self, tmp_path: Path
    ) -> None:
        store_path = tmp_path / "vectors.jsonl"
        store = VectorStore(store_path)

        # Create a vector WITHOUT files_touched
        vid = store.create_vector({
            "feature_id": 1,
            "feature_name": "old-feature",
            "campaign_id": "camp-001",
            "build_order_position": 1,
            "timestamp": "2026-03-06T00:00:00Z",
        })
        store.update_section(vid, "build_signals_v1", {
            "build_success": True,
            # No files_touched
        })

        log_dir = tmp_path / "logs"
        _write_json(log_dir / "phase-4a" / "failure-catalog.v1.json",
                     _make_failure_catalog())
        _write_json(log_dir / "phase-4b" / "rca-report.v1.json",
                     _make_rca_report())

        # Should not raise
        summary = backfill_runtime_signals(store, "camp-001", log_dir)
        assert summary["features_attributed"] == 1
        assert summary["unattributed_failures"] == 2

    def test_summary_dict_has_correct_counts(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        log_dir = tmp_path / "logs"
        _write_json(log_dir / "phase-4a" / "failure-catalog.v1.json",
                     _make_failure_catalog())
        _write_json(log_dir / "phase-4b" / "rca-report.v1.json",
                     _make_rca_report())
        _write_json(log_dir / "phase-5" / "fix-report.v1.json",
                     _make_fix_report())

        summary = backfill_runtime_signals(store, "camp-001", log_dir)

        assert "features_attributed" in summary
        assert "failures_attributed" in summary
        assert "unattributed_failures" in summary
        assert "cross_feature_interactions" in summary
        assert isinstance(summary["features_attributed"], int)
        assert isinstance(summary["failures_attributed"], int)
        assert isinstance(summary["unattributed_failures"], int)
        assert isinstance(summary["cross_feature_interactions"], int)
        # 3 features, 2 root causes attributed, 0 unattributed
        assert summary["features_attributed"] == 3
        assert summary["failures_attributed"] == 2
        assert summary["unattributed_failures"] == 0
