"""Campaign Intelligence System — Feature Vector Store.

JSONL-backed store for feature vectors with sectioned schema.
Each feature built in a campaign gets a vector with identity fields
and extensible sections populated by different signal writers.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# --- Section schema constants (for writer reference, not enforced) ---

PRE_BUILD_V1_FIELDS: list[str] = [
    "complexity_tier",
    "dependency_count",
    "depends_on_completed",
    "depends_on_pending",
    "branch_strategy",
    "estimated_file_count",
]

BUILD_SIGNALS_V1_FIELDS: list[str] = [
    "build_success",
    "retry_count",
    "retry_succeeded",
    "agent_model",
    "build_duration_seconds",
    "drift_check_passed",
    "test_check_passed",
    "injections_received",
    "component_types",
    "touches_shared_modules",
]

EVAL_SIGNALS_V1_FIELDS: list[str] = [
    "files_added",
    "files_modified",
    "lines_added",
    "lines_removed",
    "type_redeclarations",
    "framework_compliance",
    "scope_assessment",
    "integration_quality",
    "repeated_mistakes",
    "eval_notes",
]

RUNTIME_SIGNALS_V1_FIELDS: list[str] = [
    "runtime_failures_caused",
    "failure_types",
    "ac_pass_rate",
    "rca_root_causes",
    "fix_attempted",
    "fix_succeeded",
    "cross_feature_interaction",
]


@dataclass
class FeatureVector:
    """A single feature's accumulated signals across the build lifecycle.

    Identity fields are immutable after creation. Sections are extensible
    dicts populated by different signal writers (build loop, eval sidecar,
    auto-QA, etc.).
    """

    feature_id: int
    feature_name: str
    campaign_id: str
    build_order_position: int
    timestamp: str
    sections: dict[str, Any] = field(default_factory=dict)
    source: str = "local"
    schema_version: str = "1.0"


def generate_campaign_id(
    strategy: str = "default", model: str = "unknown"
) -> str:
    """Generate a unique campaign identifier.

    Format: campaign-{YYYYMMDD-HHMMSS}-{strategy}-{model}

    Args:
        strategy: Build strategy name (e.g., 'chained', 'parallel').
        model: Model identifier used for the campaign.

    Returns:
        A unique campaign ID string.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"campaign-{ts}-{strategy}-{model}"


def _vector_id(campaign_id: str, feature_id: int) -> str:
    """Compute the canonical vector ID from identity fields."""
    return f"{campaign_id}-{feature_id}"


class VectorStore:
    """JSONL-backed store for feature vectors.

    All vectors are held in memory and persisted atomically to a JSONL file.
    Each line in the file is a JSON object representing one FeatureVector.

    Args:
        store_path: Path to the JSONL file. Parent directories are created
            if they do not exist.
    """

    def __init__(self, store_path: Path) -> None:
        """Initialize the vector store.

        Args:
            store_path: Path to the JSONL backing file.
        """
        self._store_path = store_path
        self._vectors: dict[str, FeatureVector] = {}
        store_path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def create_vector(self, identity: dict[str, Any]) -> str:
        """Create a new feature vector from identity fields.

        Args:
            identity: Dict with keys: feature_id, feature_name,
                campaign_id, build_order_position, timestamp.
                Optional: source, schema_version.

        Returns:
            The vector_id (format: {campaign_id}-{feature_id}).

        Raises:
            ValueError: If a vector with the same ID already exists,
                or if required identity fields are missing.
        """
        required = [
            "feature_id",
            "feature_name",
            "campaign_id",
            "build_order_position",
            "timestamp",
        ]
        missing = [k for k in required if k not in identity]
        if missing:
            raise ValueError(f"Missing required identity fields: {missing}")

        vid = _vector_id(identity["campaign_id"], identity["feature_id"])
        if vid in self._vectors:
            raise ValueError(f"Vector already exists: {vid}")

        vec = FeatureVector(
            feature_id=identity["feature_id"],
            feature_name=identity["feature_name"],
            campaign_id=identity["campaign_id"],
            build_order_position=identity["build_order_position"],
            timestamp=identity["timestamp"],
            source=identity.get("source", "local"),
            schema_version=identity.get("schema_version", "1.0"),
        )
        self._vectors[vid] = vec
        self._persist()
        return vid

    def update_section(
        self, vector_id: str, section_name: str, data: dict[str, Any]
    ) -> None:
        """Merge data into a named section of an existing vector.

        If the section already exists, new keys are merged (existing keys
        are overwritten by the new data). If the section does not exist,
        it is created.

        Args:
            vector_id: The vector to update.
            section_name: Name of the section (e.g., 'build_signals_v1').
            data: Key-value pairs to merge into the section.

        Raises:
            KeyError: If the vector_id does not exist in the store.
        """
        if vector_id not in self._vectors:
            raise KeyError(f"Vector not found: {vector_id}")

        vec = self._vectors[vector_id]
        if section_name not in vec.sections:
            vec.sections[section_name] = {}
        vec.sections[section_name].update(data)
        self._persist()

    def get_vector(self, vector_id: str) -> FeatureVector | None:
        """Look up a vector by its ID.

        Args:
            vector_id: The vector ID to look up.

        Returns:
            The FeatureVector if found, or None.
        """
        return self._vectors.get(vector_id)

    def query_vectors(
        self, filters: dict[str, Any] | None = None
    ) -> list[FeatureVector]:
        """Return all vectors matching the given filters.

        Filters are key=value pairs matched against identity fields and
        section contents. Dotted keys (e.g., 'build_signals_v1.build_success')
        are matched against nested section data. None or empty dict returns
        all vectors.

        Args:
            filters: Optional dict of filter criteria.

        Returns:
            List of matching FeatureVector objects.
        """
        if not filters:
            return list(self._vectors.values())

        results: list[FeatureVector] = []
        for vec in self._vectors.values():
            if _matches(vec, filters):
                results.append(vec)
        return results

    def _persist(self) -> None:
        """Write all vectors to JSONL atomically via temp file + rename."""
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._store_path.parent),
            prefix=".vector_store_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                for vec in self._vectors.values():
                    f.write(json.dumps(asdict(vec), separators=(",", ":")) + "\n")
            os.rename(tmp_path, str(self._store_path))
        except BaseException:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def _load(self) -> None:
        """Read JSONL into memory dict."""
        if not self._store_path.exists():
            return
        with open(self._store_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                vec = FeatureVector(
                    feature_id=data["feature_id"],
                    feature_name=data["feature_name"],
                    campaign_id=data["campaign_id"],
                    build_order_position=data["build_order_position"],
                    timestamp=data["timestamp"],
                    sections=data.get("sections", {}),
                    source=data.get("source", "local"),
                    schema_version=data.get("schema_version", "1.0"),
                )
                vid = _vector_id(vec.campaign_id, vec.feature_id)
                self._vectors[vid] = vec


def _matches(vec: FeatureVector, filters: dict[str, Any]) -> bool:
    """Check if a vector matches all filter criteria."""
    for key, expected in filters.items():
        if "." in key:
            section_name, field_name = key.split(".", 1)
            section = vec.sections.get(section_name)
            if section is None:
                return False
            if isinstance(section, dict) and section.get(field_name) != expected:
                return False
        else:
            if getattr(vec, key, _SENTINEL) != expected:
                return False
    return True


_SENTINEL = object()
