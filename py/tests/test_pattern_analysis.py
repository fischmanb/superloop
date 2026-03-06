"""Tests for auto_sdd.lib.pattern_analysis — CIS Round 2 pattern detection."""
from __future__ import annotations

import os
from typing import Any

import pytest

from auto_sdd.lib.pattern_analysis import (
    RULES,
    Finding,
    PatternRule,
    detect_cooccurrence,
    detect_import_boundary_correlation,
    detect_retry_effectiveness,
    detect_shared_module_risk,
    detect_temporal_decay,
    detect_type_safety_trend,
    generate_campaign_findings,
    generate_risk_context,
    run_analysis,
)
from auto_sdd.lib.vector_store import FeatureVector


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_vector(
    feature_id: int = 1,
    feature_name: str = "test-feature",
    campaign_id: str = "test-campaign",
    build_order_position: int = 1,
    build_signals: dict[str, Any] | None = None,
    eval_signals: dict[str, Any] | None = None,
    convention_signals: dict[str, Any] | None = None,
    runtime_signals: dict[str, Any] | None = None,
) -> FeatureVector:
    """Create a FeatureVector with controlled section data."""
    sections: dict[str, Any] = {}
    if build_signals is not None:
        sections["build_signals_v1"] = build_signals
    if eval_signals is not None:
        sections["eval_signals_v1"] = eval_signals
    if convention_signals is not None:
        sections["convention_signals_v1"] = convention_signals
    if runtime_signals is not None:
        sections["runtime_signals_v1"] = runtime_signals
    return FeatureVector(
        feature_id=feature_id,
        feature_name=feature_name,
        campaign_id=campaign_id,
        build_order_position=build_order_position,
        timestamp="2026-03-06T00:00:00Z",
        sections=sections,
    )


# ── Dataclass construction ──────────────────────────────────────────────────


class TestDataclasses:
    def test_finding_construction(self) -> None:
        f = Finding(
            rule_name="TEST",
            confidence=0.8,
            evidence=["feat-1", "feat-2"],
            recommendation="Do something",
        )
        assert f.rule_name == "TEST"
        assert f.confidence == 0.8
        assert len(f.evidence) == 2
        assert f.recommendation == "Do something"

    def test_finding_defaults(self) -> None:
        f = Finding(rule_name="TEST", confidence=0.5)
        assert f.evidence == []
        assert f.recommendation == ""

    def test_pattern_rule_construction(self) -> None:
        rule = PatternRule(
            name="TEST_RULE",
            min_samples=3,
            detect=lambda vecs: [],
        )
        assert rule.name == "TEST_RULE"
        assert rule.min_samples == 3


# ── Feature flag ────────────────────────────────────────────────────────────


class TestFeatureFlag:
    def test_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ENABLE_PATTERN_ANALYSIS", raising=False)
        vectors = [_make_vector(feature_id=i) for i in range(10)]
        assert run_analysis(vectors) == []

    def test_disabled_when_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENABLE_PATTERN_ANALYSIS", "false")
        vectors = [_make_vector(feature_id=i) for i in range(10)]
        assert run_analysis(vectors) == []

    def test_enabled_when_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENABLE_PATTERN_ANALYSIS", "true")
        # With minimal vectors, no rules fire (below min_samples)
        vectors = [_make_vector(feature_id=i) for i in range(2)]
        result = run_analysis(vectors)
        assert isinstance(result, list)

    def test_enabled_returns_findings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENABLE_PATTERN_ANALYSIS", "true")
        # Create vectors that trigger temporal decay: 6 total, second half all fail
        vectors = []
        for i in range(3):
            vectors.append(_make_vector(
                feature_id=i,
                build_order_position=i,
                build_signals={"build_success": True, "drift_check_passed": True},
            ))
        for i in range(3, 6):
            vectors.append(_make_vector(
                feature_id=i,
                build_order_position=i,
                build_signals={"build_success": False, "drift_check_passed": True},
            ))
        result = run_analysis(vectors)
        assert len(result) > 0
        assert any(f.rule_name == "TEMPORAL_DECAY" for f in result)


# ── detect_cooccurrence ─────────────────────────────────────────────────────


class TestDetectCooccurrence:
    def test_detects_cooccurring_signals(self) -> None:
        # 8 vectors: 6 have scope=sprawling AND integration=major together
        # 2 have scope=focused, integration=clean
        vectors = []
        for i in range(6):
            vectors.append(_make_vector(
                feature_id=i,
                eval_signals={
                    "scope_assessment": "sprawling",
                    "integration_quality": "major",
                },
            ))
        for i in range(6, 8):
            vectors.append(_make_vector(
                feature_id=i,
                eval_signals={
                    "scope_assessment": "focused",
                    "integration_quality": "clean",
                },
            ))
        findings = detect_cooccurrence(vectors)
        assert len(findings) > 0
        assert any("scope_assessment" in f.recommendation for f in findings)

    def test_no_finding_for_independent_signals(self) -> None:
        # Signals are independent — equal distribution
        vectors = []
        combos = [
            ("sprawling", "clean"),
            ("sprawling", "major"),
            ("focused", "clean"),
            ("focused", "major"),
        ]
        for i, (scope, integ) in enumerate(combos * 3):
            vectors.append(_make_vector(
                feature_id=i,
                eval_signals={
                    "scope_assessment": scope,
                    "integration_quality": integ,
                },
            ))
        findings = detect_cooccurrence(vectors)
        # With perfectly uniform distribution, no co-occurrence at >2x expected
        assert len(findings) == 0

    def test_below_min_samples(self) -> None:
        vectors = [
            _make_vector(
                feature_id=i,
                eval_signals={
                    "scope_assessment": "sprawling",
                    "integration_quality": "major",
                },
            )
            for i in range(2)
        ]
        # Only 2 observations — below threshold of 3 needed for pair analysis
        findings = detect_cooccurrence(vectors)
        assert len(findings) == 0

    def test_missing_eval_signals(self) -> None:
        vectors = [_make_vector(feature_id=i) for i in range(10)]
        findings = detect_cooccurrence(vectors)
        assert findings == []


# ── detect_temporal_decay ───────────────────────────────────────────────────


class TestDetectTemporalDecay:
    def test_detects_increasing_failure_rate(self) -> None:
        vectors = []
        # First half: all succeed
        for i in range(3):
            vectors.append(_make_vector(
                feature_id=i,
                build_order_position=i,
                build_signals={"build_success": True, "drift_check_passed": True},
            ))
        # Second half: all fail
        for i in range(3, 6):
            vectors.append(_make_vector(
                feature_id=i,
                build_order_position=i,
                build_signals={"build_success": False, "drift_check_passed": True},
            ))
        findings = detect_temporal_decay(vectors)
        assert len(findings) == 1
        assert findings[0].rule_name == "TEMPORAL_DECAY"
        assert "context degradation" in findings[0].recommendation.lower() or \
               "failure rate" in findings[0].recommendation.lower()

    def test_stable_rate_no_finding(self) -> None:
        vectors = []
        # All features succeed
        for i in range(6):
            vectors.append(_make_vector(
                feature_id=i,
                build_order_position=i,
                build_signals={"build_success": True, "drift_check_passed": True},
            ))
        findings = detect_temporal_decay(vectors)
        assert findings == []

    def test_below_min_samples(self) -> None:
        vectors = [_make_vector(
            feature_id=i,
            build_order_position=i,
            build_signals={"build_success": False},
        ) for i in range(2)]
        findings = detect_temporal_decay(vectors)
        # With only 2 vectors, mid=1, should still compute but no pattern
        # Because 1 vector per half — not enough to be useful, but function runs
        assert isinstance(findings, list)

    def test_drift_failure_counts(self) -> None:
        """Drift check failure should also count as failure."""
        vectors = []
        for i in range(3):
            vectors.append(_make_vector(
                feature_id=i,
                build_order_position=i,
                build_signals={"build_success": True, "drift_check_passed": True},
            ))
        for i in range(3, 6):
            vectors.append(_make_vector(
                feature_id=i,
                build_order_position=i,
                build_signals={"build_success": True, "drift_check_passed": False},
            ))
        findings = detect_temporal_decay(vectors)
        assert len(findings) == 1


# ── detect_retry_effectiveness ──────────────────────────────────────────────


class TestDetectRetryEffectiveness:
    def test_high_retry_failure_rate(self) -> None:
        vectors = []
        # 4 features with retries, 3 still failed
        for i in range(3):
            vectors.append(_make_vector(
                feature_id=i,
                build_signals={
                    "retry_count": 2,
                    "build_success": False,
                },
            ))
        vectors.append(_make_vector(
            feature_id=3,
            build_signals={
                "retry_count": 1,
                "build_success": True,
            },
        ))
        findings = detect_retry_effectiveness(vectors)
        assert len(findings) >= 1
        fail_finding = [f for f in findings if "failing" in f.recommendation.lower() or "wasting" in f.recommendation.lower()]
        assert len(fail_finding) >= 1

    def test_high_retry_success_rate(self) -> None:
        vectors = []
        # 4 features with retries, 3 succeeded
        for i in range(3):
            vectors.append(_make_vector(
                feature_id=i,
                build_signals={
                    "retry_count": 2,
                    "build_success": True,
                },
            ))
        vectors.append(_make_vector(
            feature_id=3,
            build_signals={
                "retry_count": 1,
                "build_success": False,
            },
        ))
        findings = detect_retry_effectiveness(vectors)
        assert len(findings) >= 1
        success_finding = [f for f in findings if "need retries" in f.recommendation.lower() or "two passes" in f.recommendation.lower()]
        assert len(success_finding) >= 1

    def test_mixed_retry_outcomes(self) -> None:
        vectors = [
            _make_vector(feature_id=0, build_signals={"retry_count": 1, "build_success": True}),
            _make_vector(feature_id=1, build_signals={"retry_count": 1, "build_success": False}),
            _make_vector(feature_id=2, build_signals={"retry_count": 2, "build_success": True}),
            _make_vector(feature_id=3, build_signals={"retry_count": 1, "build_success": False}),
        ]
        findings = detect_retry_effectiveness(vectors)
        # 50/50 split — neither threshold met
        assert len(findings) == 0

    def test_no_retries(self) -> None:
        vectors = [
            _make_vector(feature_id=0, build_signals={"retry_count": 0, "build_success": True}),
            _make_vector(feature_id=1, build_signals={"retry_count": 0, "build_success": True}),
            _make_vector(feature_id=2, build_signals={"retry_count": 0, "build_success": True}),
        ]
        findings = detect_retry_effectiveness(vectors)
        assert findings == []


# ── detect_shared_module_risk ───────────────────────────────────────────────


class TestDetectSharedModuleRisk:
    def test_higher_failure_for_shared(self) -> None:
        vectors = []
        # 3 shared features, 2 fail
        vectors.append(_make_vector(feature_id=0, feature_name="db-migration",
            build_signals={"touches_shared_modules": True, "build_success": False}))
        vectors.append(_make_vector(feature_id=1, feature_name="shared-utils",
            build_signals={"touches_shared_modules": True, "build_success": False}))
        vectors.append(_make_vector(feature_id=2, feature_name="db-seed",
            build_signals={"touches_shared_modules": True, "build_success": True}))
        # 3 non-shared features, 0 fail
        for i in range(3, 6):
            vectors.append(_make_vector(
                feature_id=i,
                feature_name=f"isolated-{i}",
                build_signals={
                    "touches_shared_modules": False,
                    "build_success": True,
                },
            ))
        findings = detect_shared_module_risk(vectors)
        assert len(findings) == 1
        assert findings[0].rule_name == "SHARED_MODULE_RISK"
        assert "db-migration" in findings[0].evidence or "shared-utils" in findings[0].evidence

    def test_equal_failure_rates(self) -> None:
        vectors = []
        # 3 shared: 1 fail. 3 non-shared: 1 fail. Equal rates.
        vectors.append(_make_vector(feature_id=0,
            build_signals={"touches_shared_modules": True, "build_success": False}))
        vectors.append(_make_vector(feature_id=1,
            build_signals={"touches_shared_modules": True, "build_success": True}))
        vectors.append(_make_vector(feature_id=2,
            build_signals={"touches_shared_modules": True, "build_success": True}))
        vectors.append(_make_vector(feature_id=3,
            build_signals={"touches_shared_modules": False, "build_success": False}))
        vectors.append(_make_vector(feature_id=4,
            build_signals={"touches_shared_modules": False, "build_success": True}))
        vectors.append(_make_vector(feature_id=5,
            build_signals={"touches_shared_modules": False, "build_success": True}))
        findings = detect_shared_module_risk(vectors)
        assert findings == []

    def test_no_shared_modules(self) -> None:
        vectors = [
            _make_vector(feature_id=i, build_signals={
                "touches_shared_modules": False, "build_success": True,
            })
            for i in range(6)
        ]
        findings = detect_shared_module_risk(vectors)
        assert findings == []

    def test_no_non_shared_modules(self) -> None:
        vectors = [
            _make_vector(feature_id=i, build_signals={
                "touches_shared_modules": True, "build_success": False,
            })
            for i in range(6)
        ]
        findings = detect_shared_module_risk(vectors)
        assert findings == []


# ── run_analysis ────────────────────────────────────────────────────────────


class TestRunAnalysis:
    def test_sorted_by_confidence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENABLE_PATTERN_ANALYSIS", "true")
        # Build vectors that trigger multiple rules
        vectors = []
        # First 3: succeed, no retries, no shared
        for i in range(3):
            vectors.append(_make_vector(
                feature_id=i,
                build_order_position=i,
                build_signals={
                    "build_success": True,
                    "drift_check_passed": True,
                    "retry_count": 0,
                    "touches_shared_modules": False,
                },
            ))
        # Last 3: fail, with retries, shared
        for i in range(3, 6):
            vectors.append(_make_vector(
                feature_id=i,
                build_order_position=i,
                build_signals={
                    "build_success": False,
                    "drift_check_passed": True,
                    "retry_count": 2,
                    "touches_shared_modules": True,
                },
            ))
        result = run_analysis(vectors)
        # Should be sorted by confidence descending
        for i in range(len(result) - 1):
            assert result[i].confidence >= result[i + 1].confidence

    def test_min_samples_filtering(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENABLE_PATTERN_ANALYSIS", "true")
        # Only 2 vectors — below min_samples for all rules (min is 3)
        vectors = [
            _make_vector(
                feature_id=i,
                build_signals={
                    "build_success": False,
                    "retry_count": 2,
                    "touches_shared_modules": True,
                },
            )
            for i in range(2)
        ]
        result = run_analysis(vectors)
        assert result == []


# ── generate_risk_context ───────────────────────────────────────────────────


class TestGenerateRiskContext:
    def test_output_format(self) -> None:
        findings = [
            Finding(
                rule_name="SHARED_MODULE_RISK",
                confidence=0.8,
                evidence=["feat-1", "feat-2"],
                recommendation="Watch for shared module failures.",
            ),
        ]
        result = generate_risk_context(findings, 10)
        assert "Campaign Intelligence (10 features analyzed)" in result
        assert "SHARED_MODULE_RISK" in result
        assert "Watch for shared module failures." in result
        assert "feat-1" in result
        assert "Confidence" in result

    def test_no_findings(self) -> None:
        result = generate_risk_context([], 5)
        assert result == ""

    def test_multiple_findings(self) -> None:
        findings = [
            Finding(rule_name="RULE_A", confidence=0.9, recommendation="Fix A"),
            Finding(rule_name="RULE_B", confidence=0.7, recommendation="Fix B"),
        ]
        result = generate_risk_context(findings, 8)
        assert "RULE_A" in result
        assert "RULE_B" in result


# ── generate_campaign_findings ──────────────────────────────────────────────


class TestGenerateCampaignFindings:
    def test_produces_report_regardless_of_flag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENABLE_PATTERN_ANALYSIS", "false")
        # Enough vectors to trigger temporal decay
        vectors = []
        for i in range(3):
            vectors.append(_make_vector(
                feature_id=i,
                build_order_position=i,
                build_signals={"build_success": True, "drift_check_passed": True},
            ))
        for i in range(3, 6):
            vectors.append(_make_vector(
                feature_id=i,
                build_order_position=i,
                build_signals={"build_success": False, "drift_check_passed": True},
            ))
        report = generate_campaign_findings(vectors)
        assert "Campaign Analysis Report" in report
        assert "TEMPORAL_DECAY" in report

    def test_empty_vectors(self) -> None:
        report = generate_campaign_findings([])
        assert "Campaign Analysis Report" in report
        assert "No patterns detected" in report

    def test_no_findings_when_no_patterns(self) -> None:
        vectors = [
            _make_vector(
                feature_id=i,
                build_order_position=i,
                build_signals={"build_success": True, "drift_check_passed": True},
            )
            for i in range(6)
        ]
        report = generate_campaign_findings(vectors)
        assert "**Findings:** 0" in report


# ── Rule registry ───────────────────────────────────────────────────────────


# ── detect_import_boundary_correlation ────────────────────────────────────


class TestDetectImportBoundaryCorrelation:
    def test_correlation_detected(self) -> None:
        """Features with import boundary violations have higher failure rate."""
        vectors = []
        # 3 features with import violations, all fail
        for i in range(3):
            vectors.append(_make_vector(
                feature_id=i,
                feature_name=f"bad-import-{i}",
                convention_signals={
                    "compliance": "violated",
                    "violations": [
                        {"pattern": "import_boundaries", "assessment": "violated"},
                    ],
                },
                build_signals={"build_success": False, "drift_check_passed": True},
            ))
        # 3 features without import violations, all succeed
        for i in range(3, 6):
            vectors.append(_make_vector(
                feature_id=i,
                feature_name=f"clean-{i}",
                convention_signals={
                    "compliance": "followed",
                    "violations": [],
                },
                build_signals={"build_success": True, "drift_check_passed": True},
            ))
        findings = detect_import_boundary_correlation(vectors)
        assert len(findings) == 1
        assert findings[0].rule_name == "IMPORT_BOUNDARY_CORRELATION"

    def test_no_correlation(self) -> None:
        """No finding when failure rates are equal."""
        vectors = []
        # All succeed, some with import violations
        for i in range(6):
            has_violation = i < 3
            vectors.append(_make_vector(
                feature_id=i,
                convention_signals={
                    "compliance": "violated" if has_violation else "followed",
                    "violations": (
                        [{"pattern": "import_boundaries", "assessment": "violated"}]
                        if has_violation else []
                    ),
                },
                build_signals={"build_success": True, "drift_check_passed": True},
            ))
        findings = detect_import_boundary_correlation(vectors)
        assert findings == []

    def test_no_convention_data(self) -> None:
        """No findings when convention signals are absent."""
        vectors = [_make_vector(feature_id=i) for i in range(6)]
        findings = detect_import_boundary_correlation(vectors)
        assert findings == []

    def test_runtime_failures_counted(self) -> None:
        """Runtime failures also count as failures for correlation."""
        vectors = []
        # 3 features with import violations, runtime failures
        for i in range(3):
            vectors.append(_make_vector(
                feature_id=i,
                feature_name=f"runtime-bad-{i}",
                convention_signals={
                    "violations": [
                        {"pattern": "import_boundaries", "assessment": "violated"},
                    ],
                },
                build_signals={"build_success": True, "drift_check_passed": True},
                runtime_signals={"runtime_failures_caused": 2},
            ))
        # 3 clean features, no runtime failures
        for i in range(3, 6):
            vectors.append(_make_vector(
                feature_id=i,
                convention_signals={"violations": []},
                build_signals={"build_success": True, "drift_check_passed": True},
                runtime_signals={"runtime_failures_caused": 0},
            ))
        findings = detect_import_boundary_correlation(vectors)
        assert len(findings) == 1


# ── detect_type_safety_trend ─────────────────────────────────────────────


class TestDetectTypeSafetyTrend:
    def test_degradation_detected(self) -> None:
        """Type safety degrades over the campaign."""
        vectors = []
        # First half: clean
        for i in range(4):
            vectors.append(_make_vector(
                feature_id=i,
                build_order_position=i,
                convention_signals={"compliance": "followed"},
            ))
        # Second half: violated
        for i in range(4, 8):
            vectors.append(_make_vector(
                feature_id=i,
                build_order_position=i,
                convention_signals={"compliance": "violated"},
            ))
        findings = detect_type_safety_trend(vectors)
        assert len(findings) == 1
        assert findings[0].rule_name == "TYPE_SAFETY_TREND"

    def test_stable_compliance(self) -> None:
        """No finding when compliance is stable throughout."""
        vectors = []
        for i in range(8):
            vectors.append(_make_vector(
                feature_id=i,
                build_order_position=i,
                convention_signals={"compliance": "followed"},
            ))
        findings = detect_type_safety_trend(vectors)
        assert findings == []

    def test_too_few_samples(self) -> None:
        """No findings with fewer than 4 assessments."""
        vectors = [
            _make_vector(
                feature_id=i,
                build_order_position=i,
                convention_signals={"compliance": "violated"},
            )
            for i in range(3)
        ]
        findings = detect_type_safety_trend(vectors)
        assert findings == []

    def test_no_convention_data(self) -> None:
        """No findings when convention signals are absent."""
        vectors = [_make_vector(feature_id=i, build_order_position=i) for i in range(8)]
        findings = detect_type_safety_trend(vectors)
        assert findings == []


# ── Rule registry ───────────────────────────────────────────────────────────


class TestRuleRegistry:
    def test_six_rules_registered(self) -> None:
        rule_names = [r.name for r in RULES]
        assert "CO_OCCURRENCE" in rule_names
        assert "TEMPORAL_DECAY" in rule_names
        assert "RETRY_EFFECTIVENESS" in rule_names
        assert "SHARED_MODULE_RISK" in rule_names
        assert "IMPORT_BOUNDARY_CORRELATION" in rule_names
        assert "TYPE_SAFETY_TREND" in rule_names
        assert len(RULES) == 6

    def test_min_samples_values(self) -> None:
        by_name = {r.name: r for r in RULES}
        assert by_name["CO_OCCURRENCE"].min_samples == 5
        assert by_name["TEMPORAL_DECAY"].min_samples == 6
        assert by_name["RETRY_EFFECTIVENESS"].min_samples == 3
        assert by_name["SHARED_MODULE_RISK"].min_samples == 5
        assert by_name["IMPORT_BOUNDARY_CORRELATION"].min_samples == 5
        assert by_name["TYPE_SAFETY_TREND"].min_samples == 5
