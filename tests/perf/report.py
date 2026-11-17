"""Text report over collected runs: per-size metrics and the scaling exponent."""

import statistics

from .harness import Metrics, scaling_exponent
from .runner import Collected

MB = 1024 * 1024


def verdict(exponent: float | None) -> str:
    if exponent is None:
        return "n/a"
    if exponent < 1.2:
        return "linear"
    return "superlinear" if exponent < 1.6 else "quadratic-like"


def _mean(runs: list[Metrics], attr: str) -> float:
    return statistics.fmean(getattr(run, attr) for run in runs)


def _untraced(results: list[Metrics], scenario: str) -> dict[int, list[Metrics]]:
    grouped: dict[int, list[Metrics]] = {}
    for run in results:
        if run.scenario == scenario and not run.traced:
            grouped.setdefault(run.triples, []).append(run)
    return dict(sorted(grouped.items()))


def exponents(collected: Collected) -> dict[str, float | None]:
    scenarios = dict.fromkeys(run.scenario for run in collected.results)
    return {
        scenario: scaling_exponent([
            (triples, statistics.fmean(r.wall_s for r in runs))
            for triples, runs in _untraced(collected.results, scenario).items()
        ])
        for scenario in scenarios
    }


def format_report(collected: Collected) -> str:
    heap = {(r.scenario, r.triples): r.heap_peak_bytes for r in collected.results if r.traced}
    lines = [
        "| scenario | triples | wall s | triples/s | cpu/wall | rss MB | B/triple | heap MB | p95 ms | gc s |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for scenario in dict.fromkeys(run.scenario for run in collected.results):
        for triples, runs in _untraced(collected.results, scenario).items():
            peak = heap.get((scenario, triples))
            p95 = [r.latency_s["p95"] for r in runs if "p95" in r.latency_s]
            lines.append(
                f"| {scenario} | {triples} | {_mean(runs, 'wall_s'):.3f} | {_mean(runs, 'throughput'):.0f} | {_mean(runs, 'cpu_ratio'):.2f} "
                f"| {_mean(runs, 'rss_delta_bytes') / MB:.1f} | {_mean(runs, 'bytes_per_triple'):.0f} "
                f"| {f'{peak / MB:.1f}' if peak else '-'} | {f'{statistics.fmean(p95) * 1000:.2f}' if p95 else '-'} "
                f"| {_mean(runs, 'gc_pause_s'):.3f} |"
            )
    lines += ["", "| scenario | exponent | verdict |", "| --- | ---: | --- |"]
    for scenario, exponent in exponents(collected).items():
        lines.append(f"| {scenario} | {'-' if exponent is None else f'{exponent:.2f}'} | {verdict(exponent)} |")
    if collected.skipped:
        lines += ["", "Skipped:", *(f"- {s.scenario}[{s.triples}]: {s.reason}" for s in collected.skipped)]
    return "\n".join(lines)
