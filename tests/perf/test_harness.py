import gc
import importlib.util
import json
import time
import tracemalloc
from pathlib import Path

import pytest

from .harness import Metrics, dump, measure, os_peak_rss, percentiles, time_each, to_benchmark_json

MB = 1024 * 1024


def test_measure_records_time_and_cpu():
    def busy():
        sum(i * i for i in range(300_000))

    result = measure("busy", busy, triples=1_000)
    assert result.wall_s > 0
    assert 0 < result.cpu_s <= result.wall_s * 1.5
    assert result.throughput == pytest.approx(1_000 / result.wall_s)
    assert result.heap_peak_bytes is None


def test_measure_sees_a_memory_spike():
    held = []

    def allocate():
        held.append(b"x" * (60 * MB))
        time.sleep(0.05)

    result = measure("alloc", allocate, triples=1_000)
    assert result.rss_delta_bytes >= 40 * MB
    assert result.bytes_per_triple == result.rss_delta_bytes / 1_000


def test_measure_counts_gc_collections():
    before = list(gc.callbacks)
    result = measure("gc", gc.collect, triples=1)
    assert sum(result.gc_collections) >= 1
    assert result.gc_pause_s > 0
    assert gc.callbacks == before


def test_heap_tracing_is_opt_in_and_cleaned_up():
    result = measure("heap", lambda: list(range(500_000)), triples=1, trace_heap=True)
    assert result.heap_peak_bytes >= 10 * MB
    assert not tracemalloc.is_tracing()


def test_latency_samples_are_summarized():
    samples = time_each(lambda _: None, range(100))
    result = measure("lat", lambda: None, 1, latency_samples=lambda: samples)
    assert set(result.latency_s) == {"p50", "p95", "p99"}


def test_percentiles_use_nearest_rank():
    assert percentiles(range(1, 101)) == {"p50": 50, "p95": 95, "p99": 99}
    assert percentiles([]) == {}


def _result(wall, **kwargs):
    return Metrics("export", 1_000, wall, wall, 100, 300, [1, 0, 0], 0.0, **kwargs)


def test_benchmark_json_folds_repeats_and_keeps_metrics(tmp_path):
    out = to_benchmark_json([_result(1.0), _result(3.0)])
    (bench,) = out["benchmarks"]
    assert bench["name"] == "export[1000]"
    assert bench["stats"]["mean"] == 2.0
    assert bench["stats"]["stddev"] > 0
    assert len(bench["extra_info"]["runs"]) == 2
    path = tmp_path / "out.json"
    dump([_result(1.0)], path)
    assert json.loads(path.read_text())["benchmarks"][0]["extra_info"]["runs"][0]["rss_delta_bytes"] == 200


def test_traced_runs_never_feed_the_stats_but_supply_the_heap_peak():
    traced = _result(9.0, heap_peak_bytes=5 * MB, traced=True)
    (bench,) = to_benchmark_json([_result(1.0), traced, _result(3.0)])["benchmarks"]
    assert bench["stats"]["mean"] == 2.0
    assert bench["stats"]["rounds"] == 2
    assert bench["extra_info"]["heap_peak_bytes"] == 5 * MB
    assert all(not run["traced"] for run in bench["extra_info"]["runs"])


def test_traced_only_results_produce_no_entry():
    assert to_benchmark_json([_result(9.0, heap_peak_bytes=MB, traced=True)])["benchmarks"] == []


def test_measure_flags_traced_runs():
    assert measure("t", lambda: None, 1, trace_heap=True).traced
    assert not measure("t", lambda: None, 1).traced


def test_result_file_is_readable_by_compare_benchmarks(tmp_path):
    script = Path(__file__).parents[2] / "scripts" / "compare_benchmarks.py"
    spec = importlib.util.spec_from_file_location("compare_benchmarks", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    benchmarks = module.extract_benchmarks(to_benchmark_json([_result(1.0)]))
    assert benchmarks["export[1000]"]["mean"] == 1.0


def test_os_peak_rss_is_a_monotonic_high_water_mark():
    before = os_peak_rss()
    assert before > 0
    keep = b"x" * (40 * MB)
    assert os_peak_rss() >= before
    del keep


def test_metrics_round_trip_through_a_dict():
    original = _result(2.0, heap_peak_bytes=MB, traced=True)
    assert Metrics.from_dict(original.to_dict()) == original
