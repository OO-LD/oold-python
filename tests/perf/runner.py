"""Runs scenarios one per subprocess, so peak RSS and imports never leak between runs."""

import json
import os
import statistics
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .harness import Metrics, scaling_exponent
from .scenarios import SCENARIOS

TESTS_DIR = Path(__file__).parents[1]
DEFAULT_TIMEOUT_S = 900
SLOW_RUN_S = 60.0


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


@dataclass
class Skipped:
    scenario: str
    triples: int
    reason: str

    def as_tuple(self) -> tuple[str, int, str]:
        return self.scenario, self.triples, self.reason


@dataclass
class Collected:
    results: list[Metrics] = field(default_factory=list)
    skipped: list[Skipped] = field(default_factory=list)


def _predict(points: list[tuple[int, float]], triples: int) -> float | None:
    """Expected wall time at ``triples``, extrapolated from the sizes already run."""
    if not points:
        return None
    last_triples, last_wall = points[-1]
    exponent = scaling_exponent(points) or 1.0
    return last_wall * (triples / last_triples) ** max(exponent, 1.0)


def collect(
    sizes,
    scenarios=None,
    *,
    repeats: int = 1,
    timeout: float = DEFAULT_TIMEOUT_S,
    slow_s: float = SLOW_RUN_S,
    progress: Callable[[str], None] | None = None,
) -> Collected:
    """Per scenario and size: untraced runs, then one traced run for the heap peak.

    Sizes run in ascending order. A run is skipped, not attempted, when the
    sizes before it predict a wall time over ``timeout``, or when a smaller
    size already timed out. Runs slower than ``slow_s`` are neither repeated
    nor traced.
    """
    say = progress or (lambda _: None)
    out = Collected()
    for scenario in scenarios or SCENARIOS:
        points: list[tuple[int, float]] = []
        timed_out = False
        for triples in sorted(sizes):
            label = f"{scenario}[{triples}]"
            predicted = _predict(points, triples)
            if timed_out or (predicted is not None and predicted > timeout):
                reason = (
                    "a smaller size timed out" if timed_out else f"predicted {predicted:.0f}s exceeds {timeout:.0f}s"
                )
                out.skipped.append(Skipped(scenario, triples, reason))
                say(f"{label} skipped: {reason}")
                continue
            say(f"{label} running")
            try:
                runs = [run_scenario(scenario, triples, timeout=timeout)]
                if runs[0].wall_s < slow_s:
                    runs += [run_scenario(scenario, triples, timeout=timeout) for _ in range(repeats - 1)]
                    traced = run_scenario(scenario, triples, trace_heap=True, timeout=timeout)
                else:
                    traced = None
                    out.skipped.append(
                        Skipped(scenario, triples, f"repeats and heap trace skipped, run takes {runs[0].wall_s:.0f}s")
                    )
            except subprocess.TimeoutExpired:
                timed_out = True
                out.skipped.append(Skipped(scenario, triples, f"timed out after {timeout:.0f}s"))
                say(f"{label} timed out")
                continue
            out.results += runs + ([traced] if traced else [])
            points.append((triples, statistics.fmean(run.wall_s for run in runs)))
    return out
