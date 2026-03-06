"""Tests for the Campaign Intelligence System vector store."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from auto_sdd.lib.vector_store import (
    BUILD_SIGNALS_V1_FIELDS,
    EVAL_SIGNALS_V1_FIELDS,
    PRE_BUILD_V1_FIELDS,
    RUNTIME_SIGNALS_V1_FIELDS,
    FeatureVector,
    VectorStore,
    generate_campaign_id,
)


def _make_identity(
    feature_id: int = 1,
    feature_name: str = "Auth: Signup",
    campaign_id: str = "campaign-20260304-120000-chained-sonnet",
    build_order_position: int = 0,
    timestamp: str = "2026-03-04T12:00:00Z",
    **kwargs: Any,
) -> dict[str, Any]:
    """Build an identity dict with sensible defaults."""
    base: dict[str, Any] = {
        "feature_id": feature_id,
        "feature_name": feature_name,
        "campaign_id": campaign_id,
        "build_order_position": build_order_position,
        "timestamp": timestamp,
    }
    base.update(kwargs)
    return base


class TestCreateVector:
    """Tests for VectorStore.create_vector."""

    def test_create_returns_vector_id(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        vid = store.create_vector(_make_identity())
        assert vid == "campaign-20260304-120000-chained-sonnet-1"

    def test_create_persists_to_jsonl(self, tmp_path: Path) -> None:
        store_path = tmp_path / "vectors.jsonl"
        store = VectorStore(store_path)
        store.create_vector(_make_identity())
        lines = store_path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["feature_name"] == "Auth: Signup"

    def test_duplicate_id_raises(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        store.create_vector(_make_identity())
        with pytest.raises(ValueError, match="already exists"):
            store.create_vector(_make_identity())

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        with pytest.raises(ValueError, match="Missing required"):
            store.create_vector({"feature_id": 1})

    def test_schema_version_default(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        vid = store.create_vector(_make_identity())
        vec = store.get_vector(vid)
        assert vec is not None
        assert vec.schema_version == "1.0"

    def test_source_default_local(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        vid = store.create_vector(_make_identity())
        vec = store.get_vector(vid)
        assert vec is not None
        assert vec.source == "local"

    def test_custom_source(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        vid = store.create_vector(_make_identity(source="seed"))
        vec = store.get_vector(vid)
        assert vec is not None
        assert vec.source == "seed"


class TestUpdateSection:
    """Tests for VectorStore.update_section."""

    def test_update_creates_section(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        vid = store.create_vector(_make_identity())
        store.update_section(vid, "build_signals_v1", {"build_success": True})
        vec = store.get_vector(vid)
        assert vec is not None
        assert vec.sections["build_signals_v1"]["build_success"] is True

    def test_update_merges_not_overwrites(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        vid = store.create_vector(_make_identity())
        store.update_section(vid, "build_signals_v1", {"build_success": True})
        store.update_section(
            vid, "build_signals_v1", {"retry_count": 2}
        )
        vec = store.get_vector(vid)
        assert vec is not None
        section = vec.sections["build_signals_v1"]
        assert section["build_success"] is True
        assert section["retry_count"] == 2

    def test_update_overwrites_existing_key(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        vid = store.create_vector(_make_identity())
        store.update_section(vid, "build_signals_v1", {"build_success": True})
        store.update_section(vid, "build_signals_v1", {"build_success": False})
        vec = store.get_vector(vid)
        assert vec is not None
        assert vec.sections["build_signals_v1"]["build_success"] is False

    def test_update_nonexistent_vector_raises(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        with pytest.raises(KeyError, match="not found"):
            store.update_section("no-such-id", "section", {"k": "v"})


class TestGetVector:
    """Tests for VectorStore.get_vector."""

    def test_get_found(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        vid = store.create_vector(_make_identity())
        vec = store.get_vector(vid)
        assert vec is not None
        assert vec.feature_id == 1

    def test_get_not_found(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        assert store.get_vector("nonexistent") is None


class TestQueryVectors:
    """Tests for VectorStore.query_vectors."""

    def test_no_filters_returns_all(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        store.create_vector(_make_identity(feature_id=1))
        store.create_vector(_make_identity(feature_id=2, feature_name="Dashboard"))
        results = store.query_vectors()
        assert len(results) == 2

    def test_none_filters_returns_all(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        store.create_vector(_make_identity())
        results = store.query_vectors(None)
        assert len(results) == 1

    def test_filter_by_campaign_id(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        store.create_vector(_make_identity(feature_id=1, campaign_id="camp-A"))
        store.create_vector(_make_identity(feature_id=2, campaign_id="camp-B"))
        results = store.query_vectors({"campaign_id": "camp-A"})
        assert len(results) == 1
        assert results[0].campaign_id == "camp-A"

    def test_filter_by_section_field(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        vid1 = store.create_vector(_make_identity(feature_id=1))
        vid2 = store.create_vector(_make_identity(feature_id=2, feature_name="Dash"))
        store.update_section(vid1, "build_signals_v1", {"build_success": True})
        store.update_section(vid2, "build_signals_v1", {"build_success": False})
        results = store.query_vectors({"build_signals_v1.build_success": True})
        assert len(results) == 1
        assert results[0].feature_id == 1

    def test_empty_store_returns_empty(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        results = store.query_vectors()
        assert results == []

    def test_filter_no_match_returns_empty(self, tmp_path: Path) -> None:
        store = VectorStore(tmp_path / "vectors.jsonl")
        store.create_vector(_make_identity())
        results = store.query_vectors({"campaign_id": "nonexistent"})
        assert results == []


class TestPersistence:
    """Tests for JSONL persistence and reload."""

    def test_reload_preserves_data(self, tmp_path: Path) -> None:
        store_path = tmp_path / "vectors.jsonl"
        store1 = VectorStore(store_path)
        vid = store1.create_vector(_make_identity())
        store1.update_section(vid, "build_signals_v1", {"build_success": True})

        # Reload from disk
        store2 = VectorStore(store_path)
        vec = store2.get_vector(vid)
        assert vec is not None
        assert vec.feature_name == "Auth: Signup"
        assert vec.sections["build_signals_v1"]["build_success"] is True

    def test_reload_preserves_multiple_vectors(self, tmp_path: Path) -> None:
        store_path = tmp_path / "vectors.jsonl"
        store1 = VectorStore(store_path)
        store1.create_vector(_make_identity(feature_id=1))
        store1.create_vector(_make_identity(feature_id=2, feature_name="Dash"))

        store2 = VectorStore(store_path)
        assert len(store2.query_vectors()) == 2

    def test_atomic_write_no_temp_files_after_persist(
        self, tmp_path: Path
    ) -> None:
        store_path = tmp_path / "vectors.jsonl"
        store = VectorStore(store_path)
        store.create_vector(_make_identity())
        # After persist, no .tmp files should remain
        tmp_files = list(tmp_path.glob(".vector_store_*.tmp"))
        assert tmp_files == []

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        store_path = tmp_path / "deep" / "nested" / "vectors.jsonl"
        store = VectorStore(store_path)
        store.create_vector(_make_identity())
        assert store_path.exists()

    def test_empty_file_loads_cleanly(self, tmp_path: Path) -> None:
        store_path = tmp_path / "vectors.jsonl"
        store_path.write_text("")
        store = VectorStore(store_path)
        assert store.query_vectors() == []


class TestGenerateCampaignId:
    """Tests for generate_campaign_id."""

    def test_format(self) -> None:
        cid = generate_campaign_id(strategy="chained", model="sonnet")
        pattern = r"^campaign-\d{8}-\d{6}-chained-sonnet$"
        assert re.match(pattern, cid), f"Unexpected format: {cid}"

    def test_defaults(self) -> None:
        cid = generate_campaign_id()
        assert "-default-unknown" in cid

    def test_uniqueness(self) -> None:
        # Two calls in same second might collide, but format is correct
        cid = generate_campaign_id(strategy="parallel", model="opus")
        assert cid.startswith("campaign-")
        assert "-parallel-opus" in cid


class TestSchemaConstants:
    """Tests for section schema field constants."""

    def test_pre_build_v1_fields_nonempty(self) -> None:
        assert len(PRE_BUILD_V1_FIELDS) > 0
        assert "complexity_tier" in PRE_BUILD_V1_FIELDS

    def test_build_signals_v1_fields_nonempty(self) -> None:
        assert len(BUILD_SIGNALS_V1_FIELDS) > 0
        assert "build_success" in BUILD_SIGNALS_V1_FIELDS

    def test_eval_signals_v1_fields_nonempty(self) -> None:
        assert len(EVAL_SIGNALS_V1_FIELDS) > 0
        assert "files_added" in EVAL_SIGNALS_V1_FIELDS

    def test_runtime_signals_v1_fields_nonempty(self) -> None:
        assert len(RUNTIME_SIGNALS_V1_FIELDS) > 0
        assert "runtime_failures_caused" in RUNTIME_SIGNALS_V1_FIELDS


class TestFeatureVectorDataclass:
    """Tests for the FeatureVector dataclass."""

    def test_defaults(self) -> None:
        vec = FeatureVector(
            feature_id=1,
            feature_name="Test",
            campaign_id="c1",
            build_order_position=0,
            timestamp="2026-01-01T00:00:00Z",
        )
        assert vec.sections == {}
        assert vec.source == "local"
        assert vec.schema_version == "1.0"
