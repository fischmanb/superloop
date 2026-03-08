"""
project_config.py — reads .sdd-config/project.yaml and sets env var defaults.

Priority chain (highest to lowest):
  1. Env var already set in environment (e.g. from shell or CI)
  2. .sdd-config/project.yaml in PROJECT_DIR
  3. Auto-detection (build_gates.detect_*) — handled downstream
  4. Hardcoded defaults in build_loop.py

Usage:
    from auto_sdd.lib.project_config import load_project_config
    load_project_config(project_dir)   # call before any _env_str() reads

The function only sets env vars that are NOT already set — it never overwrites
an explicit env var. This means the caller retains full override capability
without any special-casing.

YAML format (flat key: value, no nesting required):
    build_cmd: npm run build
    test_cmd: npx vitest run --passWithNoTests
    lint_cmd: npm run lint
    build_model: claude-sonnet-4-6
    max_features: 10  # optional — omit to build all pending features
    max_retries: 2
    agent_timeout: 1800
    auto_approve: true
    branch_strategy: chained
    min_retry_delay: 30
    drift_check: true
    post_build_steps: test,dead-code,lint

All keys are optional. Unknown keys are ignored.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# Map from project.yaml key → env var name
_KEY_TO_ENV: dict[str, str] = {
    "build_cmd": "BUILD_CHECK_CMD",
    "test_cmd": "TEST_CHECK_CMD",
    "lint_cmd": "LINT_CHECK_CMD",
    "build_model": "BUILD_MODEL",
    "agent_model": "AGENT_MODEL",
    "retry_model": "RETRY_MODEL",
    "drift_model": "DRIFT_MODEL",
    "review_model": "REVIEW_MODEL",
    "max_features": "MAX_FEATURES",
    "max_retries": "MAX_RETRIES",
    "agent_timeout": "AGENT_TIMEOUT",
    "auto_approve": "AUTO_APPROVE",
    "skip_preflight": "SKIP_PREFLIGHT",
    "branch_strategy": "BRANCH_STRATEGY",
    "min_retry_delay": "MIN_RETRY_DELAY",
    "drift_check": "DRIFT_CHECK",
    "post_build_steps": "POST_BUILD_STEPS",
}

CONFIG_FILENAME = "project.yaml"
CONFIG_DIR = ".sdd-config"


def _parse_flat_yaml(text: str) -> dict[str, str]:
    """
    Parse a flat YAML file (no nesting, no lists) into a string dict.

    Handles:
      - key: value
      - key: "quoted value"
      - # comments
      - blank lines

    Does NOT handle nested keys, multi-line values, or anchors.
    This is intentional — project.yaml is kept flat by design.
    """
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.*)', line)
        if not m:
            continue
        key = m.group(1)
        val = m.group(2).strip()
        # Strip surrounding quotes
        if len(val) >= 2 and val[0] in ('"', "'") and val[-1] == val[0]:
            val = val[1:-1]
        result[key] = val
    return result


def load_project_config(project_dir: Path) -> dict[str, str]:
    """
    Read .sdd-config/project.yaml from project_dir and apply values as
    env var defaults (never overwriting already-set env vars).

    Returns the parsed key→value dict (yaml keys, not env var names).
    Returns empty dict if the file does not exist.
    """
    config_path = project_dir / CONFIG_DIR / CONFIG_FILENAME
    if not config_path.exists():
        return {}

    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    parsed = _parse_flat_yaml(text)

    for yaml_key, value in parsed.items():
        env_key = _KEY_TO_ENV.get(yaml_key)
        if env_key is None:
            continue  # unknown key — ignore
        if os.environ.get(env_key):
            continue  # env var already set — do not override
        os.environ[env_key] = value

    return parsed
