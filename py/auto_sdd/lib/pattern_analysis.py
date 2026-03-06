"""Campaign Intelligence System — Pattern Analysis.

Pluggable rule-based pattern detection on accumulated feature vectors.
Rules detect statistical patterns (co-occurrence, temporal decay, retry
effectiveness, shared-module risk) and produce Findings that get injected
into subsequent build prompts as risk context.

Feature-flagged via ENABLE_PATTERN_ANALYSIS env var (default "false").
"""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

from auto_sdd.lib.vector_store import FeatureVector


# ── Data types ──────────────────────────────────────────────────────────────


@dataclass
class Finding:
    """A single pattern detection result, ready for injection into prompts."""

    rule_name: str
    confidence: float  # 0.0–1.0
    evidence: list[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class PatternRule:
    """A registered pattern detector."""

    name: str
    min_samples: int
    detect: Callable[[list[FeatureVector]], list[Finding]]


# ── Rule registry ───────────────────────────────────────────────────────────

RULES: list[PatternRule] = []


# ── Helper: safe section access ─────────────────────────────────────────────


def _get_build_signal(vec: FeatureVector, key: str) -> Any:
    """Return a build_signals_v1 field or None if missing."""
    section = vec.sections.get("build_signals_v1")
    if isinstance(section, dict):
        return section.get(key)
    return None


def _get_eval_signal(vec: FeatureVector, key: str) -> Any:
    """Return an eval_signals_v1 field or None if missing."""
    section = vec.sections.get("eval_signals_v1")
    if isinstance(section, dict):
        return section.get(key)
    return None


def _is_failure(vec: FeatureVector) -> bool:
    """Return True if the vector represents a failed build or drift check."""
    build_ok = _get_build_signal(vec, "build_success")
    drift_ok = _get_build_signal(vec, "drift_check_passed")
    if build_ok is False:
        return True
    if drift_ok is False:
        return True
    return False


# ── Rule 1: Co-occurrence ───────────────────────────────────────────────────


def detect_cooccurrence(vectors: list[FeatureVector]) -> list[Finding]:
    """Flag categorical signal pairs that co-occur at >2x independent rates."""
    # Categorical eval fields to check
    cat_fields = ["scope_assessment", "integration_quality", "framework_compliance"]
    # Collect non-None values per field per vector
    observations: list[dict[str, str]] = []
    for vec in vectors:
        obs: dict[str, str] = {}
        for f in cat_fields:
            val = _get_eval_signal(vec, f)
            if val is not None and isinstance(val, str) and val:
                obs[f] = val
        if obs:
            observations.append(obs)

    n = len(observations)
    if n < 2:
        return []

    findings: list[Finding] = []

    # For each pair of fields, compute co-occurrence vs independent rates
    for i in range(len(cat_fields)):
        for j in range(i + 1, len(cat_fields)):
            f1, f2 = cat_fields[i], cat_fields[j]
            # Count individual values
            counts_f1: Counter[str] = Counter()
            counts_f2: Counter[str] = Counter()
            pair_counts: Counter[tuple[str, str]] = Counter()
            both_present = 0
            for obs in observations:
                v1 = obs.get(f1)
                v2 = obs.get(f2)
                if v1 is not None and v2 is not None:
                    counts_f1[v1] += 1
                    counts_f2[v2] += 1
                    pair_counts[(v1, v2)] += 1
                    both_present += 1

            if both_present < 3:
                continue

            for (v1, v2), co_count in pair_counts.items():
                rate_f1 = counts_f1[v1] / both_present
                rate_f2 = counts_f2[v2] / both_present
                expected = rate_f1 * rate_f2
                actual = co_count / both_present

                if expected > 0 and actual > 2 * expected and co_count >= 2:
                    # Find evidence: feature names where this co-occurrence happened
                    evidence: list[str] = []
                    for vec in vectors:
                        ev1 = _get_eval_signal(vec, f1)
                        ev2 = _get_eval_signal(vec, f2)
                        if ev1 == v1 and ev2 == v2:
                            evidence.append(vec.feature_name)

                    confidence = min(1.0, actual / (2 * expected) * 0.5 + 0.3)
                    findings.append(Finding(
                        rule_name="CO_OCCURRENCE",
                        confidence=round(confidence, 2),
                        evidence=evidence,
                        recommendation=(
                            f"{f1}={v1} and {f2}={v2} co-occur at "
                            f"{actual:.0%} vs {expected:.0%} expected independently. "
                            f"Watch for this combination in upcoming features."
                        ),
                    ))

    return findings


RULES.append(PatternRule(
    name="CO_OCCURRENCE",
    min_samples=5,
    detect=detect_cooccurrence,
))


# ── Rule 2: Temporal decay ──────────────────────────────────────────────────


def detect_temporal_decay(vectors: list[FeatureVector]) -> list[Finding]:
    """Flag if second-half failure rate is >2x first-half."""
    sorted_vecs = sorted(vectors, key=lambda v: v.build_order_position)
    mid = len(sorted_vecs) // 2
    if mid == 0:
        return []

    first_half = sorted_vecs[:mid]
    second_half = sorted_vecs[mid:]

    first_failures = sum(1 for v in first_half if _is_failure(v))
    second_failures = sum(1 for v in second_half if _is_failure(v))

    first_rate = first_failures / len(first_half)
    second_rate = second_failures / len(second_half)

    if first_rate == 0 and second_failures > 0:
        # First half clean, second half has failures — strong signal
        return [Finding(
            rule_name="TEMPORAL_DECAY",
            confidence=round(min(1.0, 0.5 + second_rate * 0.5), 2),
            evidence=[
                f"First half ({len(first_half)} features): "
                f"{first_failures} failures ({first_rate:.0%})",
                f"Second half ({len(second_half)} features): "
                f"{second_failures} failures ({second_rate:.0%})",
            ],
            recommendation=(
                "Failure rate increased from first half to second half of "
                "campaign. Possible context degradation or cascading "
                "dependencies. Keep changes minimal and verify independently."
            ),
        )]

    if first_rate > 0 and second_rate > 2 * first_rate:
        return [Finding(
            rule_name="TEMPORAL_DECAY",
            confidence=round(min(1.0, second_rate / (2 * first_rate) * 0.5 + 0.2), 2),
            evidence=[
                f"First half ({len(first_half)} features): "
                f"{first_failures} failures ({first_rate:.0%})",
                f"Second half ({len(second_half)} features): "
                f"{second_failures} failures ({second_rate:.0%})",
            ],
            recommendation=(
                "Failure rate increased from first half to second half of "
                "campaign. Possible context degradation or cascading "
                "dependencies. Keep changes minimal and verify independently."
            ),
        )]

    return []


RULES.append(PatternRule(
    name="TEMPORAL_DECAY",
    min_samples=6,
    detect=detect_temporal_decay,
))


# ── Rule 3: Retry effectiveness ─────────────────────────────────────────────


def detect_retry_effectiveness(vectors: list[FeatureVector]) -> list[Finding]:
    """Flag if retries consistently fail or consistently succeed."""
    retried: list[FeatureVector] = []
    for vec in vectors:
        rc = _get_build_signal(vec, "retry_count")
        if rc is not None and rc > 0:
            retried.append(vec)

    if not retried:
        return []

    succeeded = sum(
        1 for v in retried
        if _get_build_signal(v, "build_success") is True
    )
    failed = len(retried) - succeeded
    total = len(retried)

    findings: list[Finding] = []
    failure_rate = failed / total
    success_rate = succeeded / total

    if failure_rate > 0.7:
        evidence = [
            f"{failed}/{total} features failed even after retry",
        ]
        for v in retried:
            if _get_build_signal(v, "build_success") is not True:
                evidence.append(
                    f"  {v.feature_name}: "
                    f"{_get_build_signal(v, 'retry_count')} retries, still failed"
                )
        findings.append(Finding(
            rule_name="RETRY_EFFECTIVENESS",
            confidence=round(min(1.0, failure_rate), 2),
            evidence=evidence,
            recommendation=(
                "Retries are mostly failing — wasting build time. Consider "
                "improving the initial prompt or reducing retry budget."
            ),
        ))

    if success_rate > 0.7:
        evidence = [
            f"{succeeded}/{total} features succeeded only after retry",
        ]
        for v in retried:
            if _get_build_signal(v, "build_success") is True:
                evidence.append(
                    f"  {v.feature_name}: "
                    f"succeeded after {_get_build_signal(v, 'retry_count')} retries"
                )
        findings.append(Finding(
            rule_name="RETRY_EFFECTIVENESS",
            confidence=round(min(1.0, success_rate * 0.8), 2),
            evidence=evidence,
            recommendation=(
                "Features consistently need retries to succeed. The initial "
                "prompt or model may need adjustment — features that reliably "
                "need two passes indicate a systematic gap."
            ),
        ))

    return findings


RULES.append(PatternRule(
    name="RETRY_EFFECTIVENESS",
    min_samples=3,
    detect=detect_retry_effectiveness,
))


# ── Rule 4: Shared module risk ──────────────────────────────────────────────


def detect_shared_module_risk(vectors: list[FeatureVector]) -> list[Finding]:
    """Flag if shared-module features fail at >2x the rate of non-shared."""
    shared: list[FeatureVector] = []
    non_shared: list[FeatureVector] = []

    for vec in vectors:
        touches = _get_build_signal(vec, "touches_shared_modules")
        if touches is True:
            shared.append(vec)
        elif touches is False:
            non_shared.append(vec)

    if not shared or not non_shared:
        return []

    shared_fail = sum(1 for v in shared if _is_failure(v))
    non_shared_fail = sum(1 for v in non_shared if _is_failure(v))

    shared_rate = shared_fail / len(shared)
    non_shared_rate = non_shared_fail / len(non_shared)

    if non_shared_rate == 0 and shared_fail > 0:
        evidence = [
            f"Shared module features: {shared_fail}/{len(shared)} failed "
            f"({shared_rate:.0%})",
            f"Non-shared features: {non_shared_fail}/{len(non_shared)} failed "
            f"({non_shared_rate:.0%})",
        ]
        evidence.extend(
            v.feature_name for v in shared if _is_failure(v)
        )
        return [Finding(
            rule_name="SHARED_MODULE_RISK",
            confidence=round(min(1.0, 0.5 + shared_rate * 0.5), 2),
            evidence=evidence,
            recommendation=(
                "Features touching shared modules fail more often than "
                "isolated features. Verify server/client component boundaries "
                "and integration points before committing."
            ),
        )]

    if non_shared_rate > 0 and shared_rate > 2 * non_shared_rate:
        evidence = [
            f"Shared module features: {shared_fail}/{len(shared)} failed "
            f"({shared_rate:.0%})",
            f"Non-shared features: {non_shared_fail}/{len(non_shared)} failed "
            f"({non_shared_rate:.0%})",
        ]
        evidence.extend(
            v.feature_name for v in shared if _is_failure(v)
        )
        return [Finding(
            rule_name="SHARED_MODULE_RISK",
            confidence=round(min(1.0, shared_rate / (2 * non_shared_rate) * 0.5 + 0.3), 2),
            evidence=evidence,
            recommendation=(
                "Features touching shared modules fail more often than "
                "isolated features. Verify server/client component boundaries "
                "and integration points before committing."
            ),
        )]

    return []


RULES.append(PatternRule(
    name="SHARED_MODULE_RISK",
    min_samples=5,
    detect=detect_shared_module_risk,
))


# ── Rule 5: Import boundary correlation ───────────────────────────────────


def _get_convention_signal(vec: FeatureVector, key: str) -> Any:
    """Return a convention_signals_v1 field or None if missing."""
    section = vec.sections.get("convention_signals_v1")
    if isinstance(section, dict):
        return section.get(key)
    return None


def _get_runtime_signal(vec: FeatureVector, key: str) -> Any:
    """Return a runtime_signals_v1 field or None if missing."""
    section = vec.sections.get("runtime_signals_v1")
    if isinstance(section, dict):
        return section.get(key)
    return None


def detect_import_boundary_correlation(
    vectors: list[FeatureVector],
) -> list[Finding]:
    """Flag correlation between import boundary violations and failures."""
    with_violations: list[FeatureVector] = []
    without_violations: list[FeatureVector] = []

    for vec in vectors:
        violations = _get_convention_signal(vec, "violations")
        if not isinstance(violations, list):
            continue
        has_import_violation = any(
            isinstance(v, dict) and v.get("pattern") == "import_boundaries"
            for v in violations
        )
        if has_import_violation:
            with_violations.append(vec)
        else:
            without_violations.append(vec)

    if not with_violations or not without_violations:
        return []

    # Check failure rates (build failure or runtime failure)
    def _has_failure(vec: FeatureVector) -> bool:
        if _is_failure(vec):
            return True
        runtime_failures = _get_runtime_signal(vec, "runtime_failures_caused")
        if isinstance(runtime_failures, int) and runtime_failures > 0:
            return True
        return False

    with_fail = sum(1 for v in with_violations if _has_failure(v))
    without_fail = sum(1 for v in without_violations if _has_failure(v))

    with_rate = with_fail / len(with_violations)
    without_rate = without_fail / len(without_violations) if without_violations else 0

    if without_rate == 0 and with_fail > 0:
        return [Finding(
            rule_name="IMPORT_BOUNDARY_CORRELATION",
            confidence=round(min(1.0, 0.5 + with_rate * 0.5), 2),
            evidence=[
                f"Features with import boundary violations: "
                f"{with_fail}/{len(with_violations)} failed ({with_rate:.0%})",
                f"Features without: "
                f"{without_fail}/{len(without_violations)} failed ({without_rate:.0%})",
            ] + [v.feature_name for v in with_violations if _has_failure(v)][:5],
            recommendation=(
                "Import boundary violations correlate with higher failure rates. "
                "Check server/client boundaries and transitive imports before building."
            ),
        )]

    if without_rate > 0 and with_rate > 2 * without_rate:
        return [Finding(
            rule_name="IMPORT_BOUNDARY_CORRELATION",
            confidence=round(min(1.0, with_rate / (2 * without_rate) * 0.5 + 0.3), 2),
            evidence=[
                f"Features with import boundary violations: "
                f"{with_fail}/{len(with_violations)} failed ({with_rate:.0%})",
                f"Features without: "
                f"{without_fail}/{len(without_violations)} failed ({without_rate:.0%})",
            ] + [v.feature_name for v in with_violations if _has_failure(v)][:5],
            recommendation=(
                "Import boundary violations correlate with higher failure rates. "
                "Check server/client boundaries and transitive imports before building."
            ),
        )]

    return []


RULES.append(PatternRule(
    name="IMPORT_BOUNDARY_CORRELATION",
    min_samples=5,
    detect=detect_import_boundary_correlation,
))


# ── Rule 6: Type safety trend ────────────────────────────────────────────────


def detect_type_safety_trend(vectors: list[FeatureVector]) -> list[Finding]:
    """Flag if type safety compliance degrades over the campaign."""
    sorted_vecs = sorted(vectors, key=lambda v: v.build_order_position)

    # Collect compliance assessments in order
    assessments: list[tuple[int, str]] = []
    for vec in sorted_vecs:
        compliance = _get_convention_signal(vec, "compliance")
        if isinstance(compliance, str) and compliance:
            assessments.append((vec.build_order_position, compliance))

    if len(assessments) < 4:
        return []

    mid = len(assessments) // 2
    first_half = assessments[:mid]
    second_half = assessments[mid:]

    def _violation_rate(items: list[tuple[int, str]]) -> float:
        if not items:
            return 0.0
        bad = sum(1 for _, c in items if c in ("violated", "partial"))
        return bad / len(items)

    first_rate = _violation_rate(first_half)
    second_rate = _violation_rate(second_half)

    if first_rate == 0 and second_rate > 0.3:
        return [Finding(
            rule_name="TYPE_SAFETY_TREND",
            confidence=round(min(1.0, 0.5 + second_rate * 0.5), 2),
            evidence=[
                f"First half ({len(first_half)} features): "
                f"{first_rate:.0%} convention issues",
                f"Second half ({len(second_half)} features): "
                f"{second_rate:.0%} convention issues",
            ],
            recommendation=(
                "Convention compliance is degrading over the campaign. "
                "Later features show more type safety and convention issues. "
                "Review recent code for accumulated technical debt."
            ),
        )]

    if first_rate > 0 and second_rate > 2 * first_rate:
        return [Finding(
            rule_name="TYPE_SAFETY_TREND",
            confidence=round(min(1.0, second_rate / (2 * first_rate) * 0.5 + 0.2), 2),
            evidence=[
                f"First half ({len(first_half)} features): "
                f"{first_rate:.0%} convention issues",
                f"Second half ({len(second_half)} features): "
                f"{second_rate:.0%} convention issues",
            ],
            recommendation=(
                "Convention compliance is degrading over the campaign. "
                "Later features show more type safety and convention issues. "
                "Review recent code for accumulated technical debt."
            ),
        )]

    return []


RULES.append(PatternRule(
    name="TYPE_SAFETY_TREND",
    min_samples=5,
    detect=detect_type_safety_trend,
))


# ── Analysis runner ─────────────────────────────────────────────────────────


def run_analysis(vectors: list[FeatureVector]) -> list[Finding]:
    """Run all registered pattern rules and return sorted findings.

    Gated on ENABLE_PATTERN_ANALYSIS env var (default "false").
    Returns [] immediately when disabled.
    """
    if os.environ.get("ENABLE_PATTERN_ANALYSIS", "false").lower() != "true":
        return []

    return _run_all_rules(vectors)


def _run_all_rules(vectors: list[FeatureVector]) -> list[Finding]:
    """Run all rules regardless of feature flag. Used internally."""
    findings: list[Finding] = []
    for rule in RULES:
        if len(vectors) >= rule.min_samples:
            findings.extend(rule.detect(vectors))
    findings.sort(key=lambda f: f.confidence, reverse=True)
    return findings


# ── Output formatters ───────────────────────────────────────────────────────


def generate_risk_context(findings: list[Finding], total_features: int) -> str:
    """Format findings into a risk context markdown block for prompt injection.

    Args:
        findings: Pattern analysis findings to format.
        total_features: Total number of features analyzed.

    Returns:
        Markdown string suitable for injection into build prompts.
        Empty string if no findings.
    """
    if not findings:
        return ""

    lines: list[str] = [
        f"## Campaign Intelligence ({total_features} features analyzed)",
        "",
    ]

    for f in findings:
        lines.append(f"\u26a0 {f.rule_name}: {f.recommendation}")
        if f.evidence:
            lines.append(f"  Evidence: {', '.join(f.evidence[:5])}")
        lines.append("")

    lines.append(
        f"\U0001f4ca Confidence: based on {total_features} features "
        f"in current campaign."
    )
    return "\n".join(lines)


def generate_campaign_findings(vectors: list[FeatureVector]) -> str:
    """Produce a full markdown report of all findings.

    Runs all rules regardless of the ENABLE_PATTERN_ANALYSIS feature flag.
    Intended for end-of-campaign reporting, not real-time injection.

    Args:
        vectors: All feature vectors for the campaign.

    Returns:
        Markdown report string.
    """
    findings = _run_all_rules(vectors)

    lines: list[str] = [
        "# Campaign Analysis Report",
        "",
        f"**Features analyzed:** {len(vectors)}",
        f"**Findings:** {len(findings)}",
        "",
    ]

    if not findings:
        lines.append("No patterns detected.")
        return "\n".join(lines)

    for f in findings:
        lines.append(f"### {f.rule_name}")
        lines.append(f"**Confidence:** {f.confidence:.0%}")
        lines.append(f"**Recommendation:** {f.recommendation}")
        if f.evidence:
            lines.append("**Evidence:**")
            for e in f.evidence:
                lines.append(f"- {e}")
        lines.append("")

    return "\n".join(lines)
