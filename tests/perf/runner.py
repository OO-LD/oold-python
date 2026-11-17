"""Runs scenarios one per subprocess, so peak RSS and imports never leak between runs."""

import json
import os
import subprocess
import sys
from pathlib import Path

from .harness import Metrics
from .scenarios import SCENARIOS

TESTS_DIR = Path(__file__).parents[1]
DEFAULT_TIMEOUT_S = 3600


def run_scenario(
    scenario: str, triples: int, *, trace_heap: bool = False, timeout: float = DEFAULT_TIMEOUT_S
) -> Metrics:
    command = [sys.executable, "-m", "perf.worker", scenario, str(triples)]
    if trace_heap:
        command.append("--trace-heap")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(TESTS_DIR), os.environ.get("PYTHONPATH")]))}
    done = subprocess.run(  # noqa: S603 - fixed argv, no shell
        command, capture_output=True, text=True, env=env, timeout=timeout
    )
    if done.returncode != 0:
        raise RuntimeError(f"{scenario}[{triples}] failed:\n{done.stderr[-2000:]}")
    return Metrics.from_dict(json.loads(done.stdout.strip().splitlines()[-1]))


def collect(sizes, scenarios=None, *, repeats: int = 1) -> list[Metrics]:
    """Per scenario and size: ``repeats`` untraced runs, then one traced run for the heap peak."""
    results = []
    for triples in sizes:
        for scenario in scenarios or SCENARIOS:
            results += [run_scenario(scenario, triples) for _ in range(repeats)]
            results.append(run_scenario(scenario, triples, trace_heap=True))
    return results
