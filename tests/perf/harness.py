"""Resource metrics for one measured run, and the JSON result schema.

Peak RSS is only meaningful in a fresh process, so scenarios run one per
subprocess. Heap tracing slows a run down, so it is a separate, opt-in pass:
traced runs are flagged and only contribute their heap peak to the results.
"""

import gc
import json
import math
import platform
import statistics
import threading
import time
import tracemalloc
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field

import psutil

RSS_SAMPLE_INTERVAL_S = 0.002


@dataclass
class Metrics:
    scenario: str
    triples: int
    wall_s: float
    cpu_s: float
    rss_start_bytes: int
    rss_peak_bytes: int
    gc_collections: list[int]
    gc_pause_s: float
    heap_peak_bytes: int | None = None
    traced: bool = False
    latency_s: dict[str, float] = field(default_factory=dict)
    extra: dict[str, float] = field(default_factory=dict)

    @property
    def cpu_ratio(self) -> float:
        return self.cpu_s / self.wall_s if self.wall_s else 0.0

    @property
    def throughput(self) -> float:
        """Triples per second."""
        return self.triples / self.wall_s if self.wall_s else 0.0

    @property
    def rss_delta_bytes(self) -> int:
        return self.rss_peak_bytes - self.rss_start_bytes

    @property
    def bytes_per_triple(self) -> float:
        return self.rss_delta_bytes / self.triples if self.triples else 0.0

    def to_dict(self) -> dict:
        data = asdict(self)
        data.update(
            cpu_ratio=self.cpu_ratio,
            throughput=self.throughput,
            rss_delta_bytes=self.rss_delta_bytes,
            bytes_per_triple=self.bytes_per_triple,
        )
        return data


class _RssSampler:
    """Polls RSS on a thread, since the peak is not readable portably after the fact."""

    def __init__(self):
        self._process = psutil.Process()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.start_bytes = self._process.memory_info().rss
        self.peak_bytes = self.start_bytes

    def _sample(self):
        self.peak_bytes = max(self.peak_bytes, self._process.memory_info().rss)

    def _run(self):
        while not self._stop.wait(RSS_SAMPLE_INTERVAL_S):
            self._sample()

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()
        self._sample()


class _GcWatch:
    """Counts collections per generation and the time spent in them."""

    def __init__(self):
        self.collections = [0, 0, 0]
        self.pause_s = 0.0
        self._started = 0.0

    def _callback(self, phase, info):
        if phase == "start":
            self._started = time.perf_counter()
        else:
            self.pause_s += time.perf_counter() - self._started
            self.collections[info["generation"]] += 1

    def __enter__(self):
        gc.callbacks.append(self._callback)
        return self

    def __exit__(self, *exc):
        gc.callbacks.remove(self._callback)


def percentiles(samples: Iterable[float]) -> dict[str, float]:
    """Nearest-rank p50, p95 and p99."""
    ordered = sorted(samples)
    if not ordered:
        return {}
    return {f"p{p}": ordered[max(math.ceil(p / 100 * len(ordered)) - 1, 0)] for p in (50, 95, 99)}


def time_each(fn: Callable, items: Iterable) -> list[float]:
    """Seconds taken by ``fn`` for each item, to expose per-object tail cost."""
    samples = []
    for item in items:
        started = time.perf_counter()
        fn(item)
        samples.append(time.perf_counter() - started)
    return samples


def measure(
    scenario: str,
    fn: Callable[[], object],
    triples: int,
    *,
    trace_heap: bool = False,
    latency_samples: Callable[[], Iterable[float]] | None = None,
) -> Metrics:
    """Run ``fn`` once and record time, CPU, RSS, GC and optionally the Python heap peak.

    ``latency_samples`` is called after the run and returns per-object seconds
    that ``fn`` collected itself.
    """
    gc.collect()
    if trace_heap:
        tracemalloc.start()
    try:
        with _RssSampler() as rss, _GcWatch() as gc_watch:
            cpu_started = time.process_time()
            wall_started = time.perf_counter()
            fn()
            wall_s = time.perf_counter() - wall_started
            cpu_s = time.process_time() - cpu_started
        heap_peak = tracemalloc.get_traced_memory()[1] if trace_heap else None
    finally:
        if trace_heap:
            tracemalloc.stop()
    return Metrics(
        scenario=scenario,
        triples=triples,
        wall_s=wall_s,
        cpu_s=cpu_s,
        rss_start_bytes=rss.start_bytes,
        rss_peak_bytes=rss.peak_bytes,
        gc_collections=gc_watch.collections,
        gc_pause_s=gc_watch.pause_s,
        heap_peak_bytes=heap_peak,
        traced=trace_heap,
        latency_s=percentiles(latency_samples()) if latency_samples else {},
    )


def environment() -> dict[str, str]:
    return {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine()}


def to_benchmark_json(results: list[Metrics]) -> dict:
    """The pytest-benchmark shape that ``scripts/compare_benchmarks.py`` reads.

    Repeated untraced runs of one scenario and size are folded into one entry,
    which gives the stddev. Traced runs are slowed by tracemalloc, so they never
    feed the stats: only their heap peak is attached, under ``extra_info``.
    """
    grouped: dict[str, list[Metrics]] = {}
    heap_peaks: dict[str, int] = {}
    for result in results:
        name = f"{result.scenario}[{result.triples}]"
        if result.traced:
            heap_peaks[name] = max(heap_peaks.get(name, 0), result.heap_peak_bytes or 0)
        else:
            grouped.setdefault(name, []).append(result)
    benchmarks = []
    for name, runs in grouped.items():
        walls = [run.wall_s for run in runs]
        benchmarks.append({
            "name": name,
            "stats": {
                "mean": statistics.fmean(walls),
                "median": statistics.median(walls),
                "stddev": statistics.stdev(walls) if len(walls) > 1 else 0.0,
                "min": min(walls),
                "max": max(walls),
                "rounds": len(walls),
            },
            "extra_info": {"runs": [run.to_dict() for run in runs], "heap_peak_bytes": heap_peaks.get(name)},
        })
    return {"machine_info": environment(), "benchmarks": benchmarks}


def dump(results: list[Metrics], path) -> None:
    with open(path, "w") as handle:
        json.dump(to_benchmark_json(results), handle, indent=2)
