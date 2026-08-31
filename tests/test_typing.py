"""The link and query APIs must keep their static types.

``tests/typing/`` states them with ``assert_type``; pyright and ty verify them.
Both are run over the whole directory - the contract has to hold in either.

ty is pointed at the interpreter running the tests rather than at the configured
``./.venv``. An environment without pydantic does not fail: imports resolve to
``Unknown``, models report a spurious ``conflicting-metaclass``, and every
``assert_type`` in here passes vacuously.

Each checker is skipped when it is not installed, so the suite stays runnable
without a node toolchain or ty on PATH.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROBE_DIR = Path(__file__).parent / "typing"
REPO_ROOT = Path(__file__).parent.parent


def _pyright_command() -> list[str] | None:
    direct = shutil.which("pyright")
    if direct:
        return [direct]
    npx = shutil.which("npx")
    return [npx, "--no-install", "pyright"] if npx else None


def test_pyright_static_types():
    command = _pyright_command()
    if command is None:
        pytest.skip("pyright not installed")
    proc = subprocess.run(  # noqa: S603
        [*command, "--project", str(PROBE_DIR), "--outputjson"],
        capture_output=True,
        text=True,
    )
    if not proc.stdout.strip():
        pytest.skip(f"pyright unavailable: {proc.stderr[-300:]}")
    diagnostics = json.loads(proc.stdout)["generalDiagnostics"]
    problems = [d for d in diagnostics if d["severity"] in ("error", "warning")]
    assert not problems, "\n".join(f"{d['file']}:{d['range']['start']['line'] + 1} {d['message']}" for d in problems)


def test_ty_static_types():
    """The same contract has to hold in ty - it is what downstream uses."""
    ty = shutil.which("ty")
    if ty is None:
        pytest.skip("ty not installed")
    proc = subprocess.run(  # noqa: S603
        [ty, "check", "--python", sys.prefix, "tests/typing"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stdout[-3000:] or proc.stderr[-3000:]
