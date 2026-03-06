"""Tests for auto_sdd.lib.convention_checks — comprehensive coverage."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from auto_sdd.lib.convention_checks import (
    ConventionCheckResult,
    ConventionViolation,
    check_code_duplication,
    check_error_handling,
    check_import_boundaries,
    check_type_safety,
    load_eval_config,
    run_convention_checks,
)


# ── Dataclass construction ──────────────────────────────────────────────────


class TestConventionViolation:
    def test_construction(self) -> None:
        v = ConventionViolation(
            pattern="import_boundaries",
            assessment="violated",
            evidence="client/foo.ts: imports from server/db.ts",
            severity="correctness",
        )
        assert v.pattern == "import_boundaries"
        assert v.assessment == "violated"
        assert v.evidence == "client/foo.ts: imports from server/db.ts"
        assert v.severity == "correctness"


class TestConventionCheckResult:
    def test_construction(self) -> None:
        v = ConventionViolation(
            pattern="type_safety",
            assessment="deviated",
            evidence="foo.ts: 2 any annotations",
            severity="maintainability",
        )
        r = ConventionCheckResult(
            compliance="partial",
            violations=[v],
            checks_run=["type_safety"],
        )
        assert r.compliance == "partial"
        assert len(r.violations) == 1
        assert r.checks_run == ["type_safety"]

    def test_defaults(self) -> None:
        r = ConventionCheckResult(compliance="followed")
        assert r.violations == []
        assert r.checks_run == []


# ── check_import_boundaries ─────────────────────────────────────────────────


class TestCheckImportBoundaries:
    def test_server_to_client_violation(self, tmp_path: Path) -> None:
        """Server file importing from client directory is a violation."""
        (tmp_path / "server").mkdir()
        (tmp_path / "server" / "handler.ts").write_text(
            'import { Button } from "../client/components/Button";\n'
        )
        violations = check_import_boundaries(tmp_path, ["server/handler.ts"])
        assert len(violations) >= 1
        assert violations[0].pattern == "import_boundaries"
        assert violations[0].severity == "correctness"
        assert "client" in violations[0].evidence

    def test_client_to_server_violation(self, tmp_path: Path) -> None:
        """Client file importing from server directory is a violation."""
        (tmp_path / "client").mkdir()
        (tmp_path / "client" / "page.ts").write_text(
            'import { getUser } from "../server/api";\n'
        )
        violations = check_import_boundaries(tmp_path, ["client/page.ts"])
        assert len(violations) >= 1
        assert "server" in violations[0].evidence

    def test_clean_imports(self, tmp_path: Path) -> None:
        """Client file importing from other client code is fine."""
        (tmp_path / "client").mkdir()
        (tmp_path / "client" / "page.ts").write_text(
            'import { Button } from "./components/Button";\n'
        )
        violations = check_import_boundaries(tmp_path, ["client/page.ts"])
        assert violations == []

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """Non-existent file returns no violations."""
        violations = check_import_boundaries(tmp_path, ["nonexistent.ts"])
        assert violations == []

    def test_transitive_import_violation(self, tmp_path: Path) -> None:
        """Client importing a file that transitively imports server code."""
        (tmp_path / "client").mkdir()
        (tmp_path / "client" / "utils.ts").write_text(
            'import { dbQuery } from "../server/db";\n'
            "export const helper = () => dbQuery();\n"
        )
        (tmp_path / "client" / "page.ts").write_text(
            'import { helper } from "./utils";\n'
        )
        violations = check_import_boundaries(
            tmp_path, ["client/page.ts"]
        )
        assert any("transitively" in v.evidence for v in violations)

    def test_python_imports(self, tmp_path: Path) -> None:
        """Python server file importing from client directory."""
        (tmp_path / "server").mkdir()
        (tmp_path / "server" / "app.py").write_text(
            "from client.components import Widget\n"
        )
        violations = check_import_boundaries(tmp_path, ["server/app.py"])
        assert len(violations) >= 1
        assert "client" in violations[0].evidence


# ── check_type_safety ───────────────────────────────────────────────────────


class TestCheckTypeSafety:
    def test_ts_many_any_violated(self, tmp_path: Path) -> None:
        """TypeScript file with many 'any' is a violation."""
        code = "\n".join([
            "const a: any = 1;",
            "const b: any = 2;",
            "const c: any = 3;",
            "const d: any = 4;",
            "const e: any = 5;",
        ])
        (tmp_path / "bad.ts").write_text(code)
        violations = check_type_safety(tmp_path, ["bad.ts"], threshold=3)
        assert len(violations) == 1
        assert violations[0].assessment == "violated"
        assert violations[0].pattern == "type_safety"

    def test_ts_few_any_deviated(self, tmp_path: Path) -> None:
        """TypeScript file with few 'any' is a deviation."""
        code = "const a: any = 1;\nconst b: string = 'hello';\n"
        (tmp_path / "ok.ts").write_text(code)
        violations = check_type_safety(tmp_path, ["ok.ts"], threshold=3)
        assert len(violations) == 1
        assert violations[0].assessment == "deviated"

    def test_ts_zero_any_clean(self, tmp_path: Path) -> None:
        """TypeScript file with no 'any' is clean."""
        code = "const a: string = 'hello';\nconst b: number = 42;\n"
        (tmp_path / "clean.ts").write_text(code)
        violations = check_type_safety(tmp_path, ["clean.ts"])
        assert violations == []

    def test_python_untyped_params(self, tmp_path: Path) -> None:
        """Python file with untyped function parameters."""
        code = (
            "def process(data, count, label):\n"
            "    return data\n"
            "\n"
            "def typed(data: str, count: int) -> str:\n"
            "    return data\n"
        )
        (tmp_path / "untyped.py").write_text(code)
        violations = check_type_safety(tmp_path, ["untyped.py"], threshold=2)
        assert len(violations) == 1
        assert violations[0].pattern == "type_safety"
        assert "untyped" in violations[0].evidence.lower()

    def test_python_self_cls_ignored(self, tmp_path: Path) -> None:
        """Python self/cls params should not count as untyped."""
        code = (
            "class Foo:\n"
            "    def method(self, x: int) -> None:\n"
            "        pass\n"
            "    @classmethod\n"
            "    def create(cls, y: str) -> 'Foo':\n"
            "        pass\n"
        )
        (tmp_path / "typed_class.py").write_text(code)
        violations = check_type_safety(tmp_path, ["typed_class.py"])
        assert violations == []

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """Non-existent file returns no violations."""
        violations = check_type_safety(tmp_path, ["ghost.ts"])
        assert violations == []


# ── check_code_duplication ──────────────────────────────────────────────────


class TestCheckCodeDuplication:
    def test_duplicate_strings_across_files(self, tmp_path: Path) -> None:
        """Duplicate string literals across files detected."""
        long_string = "This is a very long string that should be deduplicated across files"
        (tmp_path / "a.ts").write_text(f'const msg = "{long_string}";\n')
        (tmp_path / "b.ts").write_text(f'const err = "{long_string}";\n')
        violations = check_code_duplication(tmp_path, ["a.ts", "b.ts"])
        assert any(v.pattern == "code_duplication" for v in violations)

    def test_duplicate_function_bodies(self, tmp_path: Path) -> None:
        """Near-identical function bodies across files detected."""
        body = (
            "def process(data: list) -> list:\n"
            "    result = []\n"
            "    for item in data:\n"
            "        if item > 0:\n"
            "            result.append(item * 2)\n"
            "        else:\n"
            "            result.append(0)\n"
            "    return result\n"
        )
        (tmp_path / "mod_a.py").write_text(body)
        (tmp_path / "mod_b.py").write_text(body)
        violations = check_code_duplication(
            tmp_path, ["mod_a.py", "mod_b.py"], min_function_lines=5
        )
        assert any(
            v.pattern == "code_duplication" and v.assessment == "violated"
            for v in violations
        )

    def test_no_duplicates(self, tmp_path: Path) -> None:
        """No duplicates when files have unique content."""
        (tmp_path / "unique_a.py").write_text("x = 1\n")
        (tmp_path / "unique_b.py").write_text("y = 2\n")
        violations = check_code_duplication(
            tmp_path, ["unique_a.py", "unique_b.py"]
        )
        assert violations == []

    def test_short_strings_ignored(self, tmp_path: Path) -> None:
        """Short strings under threshold are not flagged."""
        (tmp_path / "short_a.ts").write_text('const x = "short";\n')
        (tmp_path / "short_b.ts").write_text('const y = "short";\n')
        violations = check_code_duplication(
            tmp_path, ["short_a.ts", "short_b.ts"], min_string_length=20
        )
        assert violations == []


# ── check_error_handling ────────────────────────────────────────────────────


class TestCheckErrorHandling:
    def test_empty_catch_ts(self, tmp_path: Path) -> None:
        """Empty catch block in TypeScript is a violation."""
        code = "try { doStuff(); } catch(e) {}\n"
        (tmp_path / "bad.ts").write_text(code)
        violations = check_error_handling(tmp_path, ["bad.ts"])
        assert len(violations) >= 1
        assert violations[0].pattern == "error_handling"
        assert violations[0].assessment == "violated"
        assert "empty catch" in violations[0].evidence

    def test_log_only_catch_ts(self, tmp_path: Path) -> None:
        """Log-only catch block in TypeScript is a deviation."""
        code = "try { doStuff(); } catch(e) { console.log(e) }\n"
        (tmp_path / "logonly.ts").write_text(code)
        violations = check_error_handling(tmp_path, ["logonly.ts"])
        assert any(v.assessment == "deviated" for v in violations)

    def test_bare_except_python(self, tmp_path: Path) -> None:
        """Bare except in Python is a violation."""
        code = "try:\n    x = 1\nexcept:\n    pass\n"
        (tmp_path / "bare.py").write_text(code)
        violations = check_error_handling(tmp_path, ["bare.py"])
        assert any(
            v.pattern == "error_handling" and "bare except" in v.evidence
            for v in violations
        )

    def test_except_pass_python(self, tmp_path: Path) -> None:
        """except Exception: pass in Python is a violation."""
        code = "try:\n    x = 1\nexcept Exception:\n    pass\n"
        (tmp_path / "passonly.py").write_text(code)
        violations = check_error_handling(tmp_path, ["passonly.py"])
        assert any(
            v.pattern == "error_handling" and "pass" in v.evidence
            for v in violations
        )

    def test_proper_error_handling(self, tmp_path: Path) -> None:
        """Proper error handling produces no violations."""
        code = (
            "try:\n"
            "    x = int(input())\n"
            "except ValueError as e:\n"
            "    logger.error('Invalid input: %s', e)\n"
            "    raise\n"
        )
        (tmp_path / "proper.py").write_text(code)
        violations = check_error_handling(tmp_path, ["proper.py"])
        # Should not flag proper error handling with raise
        bare_or_pass = [
            v for v in violations
            if "bare except" in v.evidence or "bare pass" in v.evidence
        ]
        assert bare_or_pass == []

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """Non-existent file returns no violations."""
        violations = check_error_handling(tmp_path, ["ghost.py"])
        assert violations == []


# ── run_convention_checks integration ───────────────────────────────────────


class TestRunConventionChecks:
    def test_all_checks_enabled_default(self, tmp_path: Path) -> None:
        """All checks run by default with clean files."""
        (tmp_path / "clean.py").write_text("x = 1\n")
        result = run_convention_checks(tmp_path, ["clean.py"])
        assert result.compliance == "followed"
        assert len(result.checks_run) == 4
        assert "import_boundaries" in result.checks_run
        assert "type_safety" in result.checks_run
        assert "code_duplication" in result.checks_run
        assert "error_handling" in result.checks_run

    def test_config_disables_all(self, tmp_path: Path) -> None:
        """Config can disable convention checks entirely."""
        config: dict[str, Any] = {
            "convention_checks": {"enabled": False}
        }
        result = run_convention_checks(tmp_path, ["any.py"], config=config)
        assert result.compliance == "followed"
        assert result.checks_run == []

    def test_config_disables_individual_check(self, tmp_path: Path) -> None:
        """Config can disable individual checks."""
        code = "try:\n    x = 1\nexcept:\n    pass\n"
        (tmp_path / "bad.py").write_text(code)
        config: dict[str, Any] = {
            "convention_checks": {
                "enabled": True,
                "checks": {
                    "import_boundaries": True,
                    "type_safety": True,
                    "code_duplication": True,
                    "error_handling": False,
                },
                "thresholds": {},
            }
        }
        result = run_convention_checks(tmp_path, ["bad.py"], config=config)
        assert "error_handling" not in result.checks_run
        # Should not detect the bare except since error_handling is disabled
        assert not any(v.pattern == "error_handling" for v in result.violations)

    def test_compliance_violated(self, tmp_path: Path) -> None:
        """Result shows violated when there are violations."""
        code = "try:\n    x = 1\nexcept:\n    pass\n"
        (tmp_path / "bad.py").write_text(code)
        result = run_convention_checks(tmp_path, ["bad.py"])
        assert result.compliance == "violated"

    def test_compliance_partial(self, tmp_path: Path) -> None:
        """Result shows partial when there are only deviations."""
        code = "const a: any = 1;\n"
        (tmp_path / "deviated.ts").write_text(code)
        result = run_convention_checks(tmp_path, ["deviated.ts"])
        assert result.compliance == "partial"

    def test_default_config_used_when_no_file(self, tmp_path: Path) -> None:
        """Defaults are used when no config file exists."""
        (tmp_path / "ok.py").write_text("x = 1\n")
        result = run_convention_checks(tmp_path, ["ok.py"])
        assert len(result.checks_run) == 4


# ── load_eval_config ────────────────────────────────────────────────────────


class TestLoadEvalConfig:
    def test_defaults_when_no_file(self, tmp_path: Path) -> None:
        """Returns defaults when no config file exists."""
        config = load_eval_config(tmp_path)
        cc = config.get("convention_checks", {})
        assert cc.get("enabled") is True
        assert cc.get("checks", {}).get("import_boundaries") is True

    def test_json_config_loaded(self, tmp_path: Path) -> None:
        """Loads config from .sdd-config/eval-dimensions.json."""
        config_dir = tmp_path / ".sdd-config"
        config_dir.mkdir()
        config_data = {
            "convention_checks": {
                "enabled": True,
                "checks": {
                    "import_boundaries": False,
                    "type_safety": True,
                    "code_duplication": True,
                    "error_handling": True,
                },
                "thresholds": {
                    "any_type_per_file_warn": 5,
                },
            }
        }
        (config_dir / "eval-dimensions.json").write_text(
            json.dumps(config_data)
        )
        config = load_eval_config(tmp_path)
        cc = config.get("convention_checks", {})
        assert cc["checks"]["import_boundaries"] is False
        assert cc["thresholds"]["any_type_per_file_warn"] == 5

    def test_malformed_json_returns_defaults(self, tmp_path: Path) -> None:
        """Malformed JSON falls back to defaults."""
        config_dir = tmp_path / ".sdd-config"
        config_dir.mkdir()
        (config_dir / "eval-dimensions.json").write_text("not valid json{{{")
        config = load_eval_config(tmp_path)
        # Should get defaults
        assert "convention_checks" in config

    def test_malformed_json_string_returns_defaults(self, tmp_path: Path) -> None:
        """JSON that parses but isn't a dict falls back to defaults."""
        config_dir = tmp_path / ".sdd-config"
        config_dir.mkdir()
        (config_dir / "eval-dimensions.json").write_text('"just a string"')
        config = load_eval_config(tmp_path)
        assert "convention_checks" in config
