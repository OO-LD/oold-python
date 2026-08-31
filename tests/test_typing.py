"""The query DSL must keep its static types.

``tests/typing/query_dsl.py`` states them with ``assert_type``; pyright is what
verifies them. Skipped when pyright is not installed, so the suite stays runnable
without a node toolchain.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PROBE_DIR = Path(__file__).parent / "typing"


def _pyright_command() -> list[str] | None:
    direct = shutil.which("pyright")
    if direct:
        return [direct]
    npx = shutil.which("npx")
    if npx:
        return [npx, "--no-install", "pyright"]
    return None


def test_query_dsl_static_types():
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
