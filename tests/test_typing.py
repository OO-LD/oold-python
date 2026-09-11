"""The link and query APIs must keep their static types.

``tests/typing/`` states them with ``assert_type``; pyright and ty verify them.
Both are run over the whole directory - the contract has to hold in either.

Both checkers are pointed at the interpreter running the tests rather than at
whatever they would discover themselves. An environment without pydantic does not
fail honestly: ty resolves the imports to ``Unknown``, reports a spurious
``conflicting-metaclass`` and passes every ``assert_type`` vacuously, while
pyright reports ``Expected no type arguments`` on ``Model[...]``. Both look like
results and are not.

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


def _ty_command() -> list[str] | None:
    direct = shutil.which("ty")
    if direct:
        return [direct]
    # uv ships ty on demand; without this the test skips silently on machines
    # where ty is only ever invoked through uvx
    uvx = shutil.which("uvx")
    return [uvx, "ty"] if uvx else None


def _pyright_command() -> list[str] | None:
    direct = shutil.which("pyright")
    if direct:
        return [direct]
    uvx = shutil.which("uvx")
    if uvx:
        return [uvx, "pyright"]
    npx = shutil.which("npx")
    return [npx, "--no-install", "pyright"] if npx else None


def test_pyright_static_types():
    command = _pyright_command()
    if command is None:
        pytest.skip("pyright not installed")
    proc = subprocess.run(  # noqa: S603
        [*command, "--project", str(PROBE_DIR), "--pythonpath", sys.executable, "--outputjson"],
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
    command = _ty_command()
    if command is None:
        pytest.skip("ty not installed")
    proc = subprocess.run(  # noqa: S603
        [*command, "check", "--python", sys.prefix, "tests/typing"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stdout[-3000:] or proc.stderr[-3000:]
