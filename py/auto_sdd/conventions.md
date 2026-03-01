# Python Conventions — auto-sdd

> Every conversion agent MUST read this file before writing any code.
> This document is the single source of truth for patterns, naming, error handling,
> and interface contracts. Deviations are bugs.

## Python Version

**Minimum: 3.12**. Use 3.12+ features freely (improved typing, f-string improvements, better error messages).

## Package Structure

```
py/
├── auto_sdd/
│   ├── __init__.py          # Version string only
│   ├── lib/
│   │   ├── __init__.py      # Empty
│   │   ├── errors.py
│   │   ├── reliability.py
│   │   ├── eval_lib.py
│   │   ├── codebase_summary.py
│   │   ├── validation.py
│   │   ├── claude_wrapper.py
│   │   ├── signals.py
│   │   └── state.py
│   ├── scripts/
│   │   ├── build_loop.py
│   │   ├── eval_sidecar.py
│   │   └── ...
│   └── conventions.md       # This file
├── tests/
│   ├── conftest.py
│   ├── test_reliability.py
│   └── ...
└── pyproject.toml
```

Imports use the package path: `from auto_sdd.lib.reliability import acquire_lock`.

## Error Handling

Typed exception hierarchy. All auto-sdd exceptions inherit from `AutoSddError`.

```python
# auto_sdd/lib/errors.py

class AutoSddError(Exception):
    """Base for all auto-sdd errors."""

class BuildFailedError(AutoSddError):
    """A feature build failed (non-retryable)."""

class CreditExhaustedError(AutoSddError):
    """API credit/rate limit exhausted after all retries."""

class LockContentionError(AutoSddError):
    """Another instance holds the lock."""

class AgentTimeoutError(AutoSddError):
    """Claude agent exceeded timeout."""

class CircularDependencyError(AutoSddError):
    """Roadmap dependency graph has a cycle."""

class InvalidSpecError(AutoSddError):
    """Feature spec fails frontmatter validation."""
```

**Rules:**
- Raise specific exceptions, never bare `Exception`.
- Catch specific exceptions. `except Exception` only at script entry points for clean shutdown logging.
- Exception messages are human-readable sentences. Include the failing input when useful.
- Let exceptions propagate. Don't catch-and-log-and-continue unless the caller genuinely needs to proceed.

## Subprocess Patterns

Claude CLI invocation goes through one function: `run_claude()` in `claude_wrapper.py`.

```python
@dataclass
class ClaudeResult:
    output: str
    exit_code: int
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    session_id: str | None = None
    duration_ms: int | None = None

def run_claude(
    args: list[str],
    *,
    cost_log_path: Path | None = None,
    timeout: int = 600,
) -> ClaudeResult:
    """Invoke claude CLI, extract result, log cost.

    Args:
        args: CLI arguments (e.g., ["-p", "--dangerously-skip-permissions", prompt]).
        cost_log_path: Path to JSONL cost log. None disables logging.
        timeout: Seconds before subprocess.TimeoutExpired. Default 10 minutes.

    Returns:
        ClaudeResult with parsed output and cost metadata.

    Raises:
        AgentTimeoutError: If claude exceeds timeout.
        subprocess.CalledProcessError: If claude exits non-zero (after diagnostic capture).
    """
```

**Rules:**
- All subprocess calls use `subprocess.run()`, never `os.system()` or `os.popen()`.
- Always pass `timeout=` to subprocess calls. Default 600s (10 min), overridable per call.
- Capture stderr separately: `capture_output=True` or `stderr=subprocess.PIPE`.
- Unset `CLAUDECODE` env var before invoking claude (prevents nested-session detection).

## Logging

Use `logging` from stdlib. One logger per module.

```python
import logging

logger = logging.getLogger(__name__)
```

**Level mapping from bash:**
| Bash pattern | Python level |
|---|---|
| `log "..."` / `[INFO]` | `logger.info()` |
| `warn "..."` / `[WARN]` | `logger.warning()` |
| `error "..."` / `[ERROR]` | `logger.error()` |
| `success "..."` / `[✓]` | `logger.info()` (prefix with ✓ in message) |
| Debug/verbose | `logger.debug()` |

**Configuration** (done once at script entry point, not in libs):
```python
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
```

Build logs use a `FileHandler` added at runtime — the lib code just calls `logger.info()` and the script configures where it goes.

**Rules:**
- Libs NEVER call `logging.basicConfig()`. Only script entry points configure logging.
- No `print()` for operational messages. Use `logger`. Exception: signal emission (see below).
- Log the action and outcome, not just "entering function X".

## Signal Protocol

Signals are flat grep-parseable strings printed to stdout. This is a hard constraint from L-0028. The build loop, eval sidecar, and overnight scripts all parse signals with grep/awk.

```python
# auto_sdd/lib/signals.py

# Signal constants
FEATURE_BUILT = "FEATURE_BUILT"
BUILD_FAILED = "BUILD_FAILED"
EVAL_COMPLETE = "EVAL_COMPLETE"
EVAL_FRAMEWORK_COMPLIANCE = "EVAL_FRAMEWORK_COMPLIANCE"
EVAL_SCOPE_ASSESSMENT = "EVAL_SCOPE_ASSESSMENT"
EVAL_INTEGRATION_QUALITY = "EVAL_INTEGRATION_QUALITY"
EVAL_REPEATED_MISTAKES = "EVAL_REPEATED_MISTAKES"
EVAL_NOTES = "EVAL_NOTES"
CREDIT_EXHAUSTED = "CREDIT_EXHAUSTED"
AGENT_ERROR = "AGENT_ERROR"

def emit(signal: str, value: str) -> None:
    """Print a signal line to stdout. Grep-parseable format: 'SIGNAL_NAME: value'."""
    print(f"{signal}: {value}", flush=True)

def parse(signal_name: str, output: str) -> str:
    """Extract the last value of a named signal from multiline output."""
    ...
```

**Rules:**
- Signals are ALWAYS emitted via `signals.emit()`, never by formatting strings inline.
- Signal format is `SIGNAL_NAME: value` — colon, space, then value. No JSON, no nesting.
- Python internals can use any data structures. Signals are the boundary protocol only.
- New signals must be added as constants in signals.py first.

## File-based State I/O

State files (resume state, cost logs, build summaries) use the existing JSON/JSONL formats. No format changes during conversion — one variable at a time.

Shared patterns live in `state.py`:

```python
# auto_sdd/lib/state.py

import fcntl
import json
import tempfile
from pathlib import Path

def atomic_write(path: Path, data: str) -> None:
    """Write data to path atomically: write temp file, then rename.

    Prevents partial reads if another process reads mid-write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.stem)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(data)
        os.rename(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise

def atomic_write_json(path: Path, obj: dict | list) -> None:
    """Write JSON atomically with validation."""
    data = json.dumps(obj, indent=2) + "\n"
    atomic_write(path, data)

def read_json(path: Path) -> dict | list | None:
    """Read JSON file. Returns None if file doesn't exist."""
    if not path.exists():
        return None
    return json.loads(path.read_text())

def append_jsonl(path: Path, record: dict) -> None:
    """Append a single JSON record to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")

class FileLock:
    """Process-level file lock using fcntl.flock().

    Platform: macOS/Linux only (fcntl is Unix). No Windows support needed.

    Usage:
        lock = FileLock(Path("build.lock"))
        lock.acquire()  # raises LockContentionError if held by live process
        try:
            ...
        finally:
            lock.release()
    """
    def __init__(self, path: Path) -> None: ...
    def acquire(self) -> None: ...
    def release(self) -> None: ...
    def __enter__(self) -> "FileLock": ...
    def __exit__(self, *args: object) -> None: ...
```

**Rules:**
- All state writes use `atomic_write()` or `atomic_write_json()`. No direct `open(path, "w").write()`.
- Locking uses `FileLock` (wraps `fcntl.flock()`). Stale lock detection checks PID liveness, same as bash.
- JSONL append is the one exception to atomic write — append is already safe for single-line records.
- State format matches existing bash output exactly. A Python-written state file must be readable by bash scripts and vice versa during coexistence.

## Type Hints

All code is fully typed. `mypy --strict` must pass.

```python
# Good
def emit_topo_order(project_dir: Path) -> list[Feature]: ...

# Bad — missing return type
def emit_topo_order(project_dir: Path): ...

# Bad — using Any
def emit_topo_order(project_dir: Any) -> Any: ...
```

**Rules:**
- Use `Path` (from pathlib) for all file/directory parameters, never `str`.
- Use `list[X]`, `dict[K, V]`, `X | None` — not `List`, `Dict`, `Optional` from typing (3.12 builtins suffice).
- Define dataclasses or NamedTuples for structured return types (e.g., `ResumeState`, `ClaudeResult`, `Feature`).
- `Any` is forbidden except when wrapping genuinely untyped external data (e.g., raw JSON before validation).

## Dependencies

**stdlib + pytest only.** No third-party packages without Brian's explicit approval.

```toml
# pyproject.toml
[project]
name = "auto-sdd"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8.0", "mypy>=1.8"]
future = []  # placeholder for approved third-party deps

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

Install: `pip install -e ".[dev]"`

**Rules:**
- No click, typer, rich, or any CLI framework. Use `argparse` if scripts need CLI args.
- No requests, httpx, or HTTP libs. Claude CLI is invoked via subprocess.
- No pydantic. Use dataclasses + manual validation.
- If a future need arises, add to `[project.optional-dependencies] future` and get approval.

## Test Patterns

Framework: pytest. Tests live in `py/tests/`, one file per lib module.

**Naming:** `test_{function}_{scenario}`. Examples:
- `test_acquire_lock_succeeds_when_no_lock_exists`
- `test_acquire_lock_raises_on_live_pid`
- `test_write_state_atomic_on_crash`
- `test_validate_frontmatter_missing_feature_field`

**Assertions:** Plain `assert` with descriptive messages. No `unittest.TestCase`, no `self.assertEqual`.

```python
# Good
assert result.exit_code == 0, f"Expected success, got exit {result.exit_code}"

# Bad
self.assertEqual(result.exit_code, 0)
```

**Fixtures** in `conftest.py`:

```python
# py/tests/conftest.py
import pytest
from pathlib import Path
import tempfile
import shutil

@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """A temporary project directory with minimal structure."""
    (tmp_path / "src").mkdir()
    (tmp_path / ".specs").mkdir()
    (tmp_path / ".specs" / "roadmap.md").touch()
    return tmp_path

@pytest.fixture
def sample_spec(tmp_path: Path) -> Path:
    """A valid feature spec file with frontmatter."""
    spec = tmp_path / "feature.md"
    spec.write_text(
        "---\n"
        "feature: test-feature\n"
        "domain: core\n"
        "status: pending\n"
        "---\n"
        "# Test Feature\n"
    )
    return spec

@pytest.fixture
def mock_claude_output(tmp_path: Path) -> Path:
    """A file containing mock claude JSON output."""
    output = tmp_path / "claude-output.json"
    output.write_text('{"result": "mock output", "total_cost_usd": 0.01}')
    return output
```

**Rules:**
- Every function in the lib gets at least one test. Edge cases (empty input, missing file, invalid JSON) get their own tests.
- Tests must not depend on network, filesystem state outside tmp_path, or running processes.
- Use `pytest.raises(SpecificError)` for exception testing, never bare try/except in tests.
- No mocking unless the alternative is hitting the real Claude API. Prefer real files in tmp_path over mocks.

## Interface Stubs

These are the function signatures that `build-loop-local.py` (Phase 4) will call from each lib module. Phase 1 agents MUST implement these exact signatures. Additional helper functions are fine, but these contracts are non-negotiable.

### reliability.py

```python
from pathlib import Path
from dataclasses import dataclass
from typing import Callable

@dataclass
class ResumeState:
    feature_index: int
    branch_strategy: str
    completed_features: list[str]
    current_branch: str
    timestamp: str

@dataclass
class Feature:
    id: int
    name: str
    complexity: str

@dataclass
class DriftPair:
    spec_file: Path
    source_files: str

# NOTE: write_state accepts list[str] directly — no separate serialization step.
# In bash, completed_features_json() serialized the list to a JSON string before passing
# to write_state. In Python, write_state handles serialization internally.
# completed_features_json() is intentionally removed — it was a bash-ism.
def acquire_lock(lock_file: Path) -> None: ...
def release_lock(lock_file: Path) -> None: ...
def write_state(state_file: Path, feature_index: int, strategy: str, completed_features: list[str], current_branch: str) -> None: ...
def read_state(state_file: Path) -> ResumeState | None: ...
def clean_state(state_file: Path) -> None: ...
def run_agent_with_backoff(output_file: Path, cmd: list[str], *, max_retries: int = 5, backoff_max: int = 60) -> int: ...
def truncate_for_context(file_path: Path, max_tokens: int = 100_000) -> str: ...
def check_circular_deps(project_dir: Path) -> None: ...
def emit_topo_order(project_dir: Path) -> list[Feature]: ...
def get_cpu_count() -> int: ...
def run_parallel_drift_checks(pairs: list[DriftPair], check_fn: Callable[[Path, str], bool]) -> bool: ...
```

### codebase_summary.py

```python
from pathlib import Path

def generate_codebase_summary(project_dir: Path, max_lines: int = 200) -> str: ...
```

### claude_wrapper.py

```python
from pathlib import Path
from dataclasses import dataclass

@dataclass
class ClaudeResult:
    output: str
    exit_code: int
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    session_id: str | None = None
    duration_ms: int | None = None

def run_claude(args: list[str], *, cost_log_path: Path | None = None, timeout: int = 600) -> ClaudeResult: ...
```

### eval_lib.py

```python
from pathlib import Path
from dataclasses import dataclass

@dataclass
class MechanicalEvalResult:
    diff_stats: dict[str, int]
    type_exports_changed: list[str]
    redeclarations: list[str]
    test_files_touched: list[str]
    passed: bool

def run_mechanical_eval(project_dir: Path, commit_hash: str) -> MechanicalEvalResult: ...
def generate_eval_prompt(project_dir: Path, commit_hash: str) -> str: ...
def parse_eval_signal(signal_name: str, output: str) -> str: ...
def write_eval_result(output_dir: Path, feature_name: str, mechanical: MechanicalEvalResult, agent_output: str) -> Path: ...
```

### validation.py

```python
from pathlib import Path

def validate_frontmatter(file_path: Path, validate_only: bool = False) -> bool: ...
```

## Naming Conventions

- Files: `snake_case.py` (e.g., `codebase_summary.py`, not `codebaseSummary.py`)
- Functions: `snake_case` (e.g., `run_mechanical_eval`)
- Classes/dataclasses: `PascalCase` (e.g., `ClaudeResult`, `ResumeState`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `FEATURE_BUILT`, `MAX_CONTEXT_TOKENS`)
- Test files: `test_{module}.py` (e.g., `test_reliability.py`)
- Test functions: `test_{function}_{scenario}` (e.g., `test_acquire_lock_stale_pid_removed`)

## Conversion Changelog

Each agent MUST maintain a changelog in a comment block at the top of its output file documenting deviations from the bash original. Both the converting agent and the reviewing agent verify this log.

```python
# CONVERSION CHANGELOG (from lib/reliability.sh)
# - completed_features_json() removed: bash-ism. write_state() now accepts
#   list[str] directly and serializes internally.
# - DriftPair.source_files: was colon-delimited string in bash, now [describe decision].
# - [any other intentional deviations from bash shape]
```

This is not boilerplate — it captures WHY the Python version differs from bash. If there's nothing to log, the agent writes `# No deviations from bash interface.`

## What NOT to Do

- Don't use `os.path`. Use `pathlib.Path` everywhere. (`os` module itself is fine for `os.fdopen`, `os.rename`, etc. — the ban is specifically `os.path` string manipulation.)
- Don't use `print()` for logging. Use `logger`. (Signal emission via `signals.emit()` is the sole exception.)
- Don't catch `Exception` in lib code. Let errors propagate.
- Don't add dependencies without approval.
- Don't modify files outside your assigned conversion unit.
- Don't change the signal format. `SIGNAL_NAME: value` is the protocol.
- Don't change state file formats. Bash compatibility must be preserved during coexistence.
