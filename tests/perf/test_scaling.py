import pytest

from .dataset import BENCHMARK_SIZES, TRIPLE_SIZES
from .harness import Metrics, scaling_exponent
from .report import exponents, format_report, verdict
from .runner import Collected, Skipped, collect


def _metrics(scenario, triples, wall, **kwargs):
    return Metrics(scenario, triples, wall, wall, 100, 200, [0, 0, 0], 0.0, **kwargs)


def test_benchmark_sizes_cover_the_issue_sizes():
    assert set(TRIPLE_SIZES) <= set(BENCHMARK_SIZES)


def test_scaling_exponent_recovers_known_slopes():
    assert scaling_exponent([(1_000, 1.0), (10_000, 10.0), (100_000, 100.0)]) == pytest.approx(1.0)
    assert scaling_exponent([(1_000, 1.0), (10_000, 100.0)]) == pytest.approx(2.0)
    assert scaling_exponent([(1_000, 1.0)]) is None


@pytest.mark.parametrize(
    ("exponent", "label"), [(None, "n/a"), (1.0, "linear"), (1.4, "superlinear"), (1.9, "quadratic-like")]
)
def test_verdict(exponent, label):
    assert verdict(exponent) == label


def test_report_lists_sizes_exponent_and_skips():
    collected = Collected(
        results=[
            _metrics("export", 1_000, 1.0),
            _metrics("export", 10_000, 10.0),
            _metrics("export", 10_000, 9.0, heap_peak_bytes=1, traced=True),
        ]
    )
    collected.skipped.append(Skipped("export", 100_000, "why"))
    report = format_report(collected)
    assert "| export | 10000 | 10.000 |" in report
    assert "| export | 1.00 | linear |" in report
    assert "export[100000]: why" in report
    assert exponents(collected)["export"] == pytest.approx(1.0)


def test_report_shows_sparql_calls_and_output_size():
    run = _metrics("export", 1_000, 1.0)
    run.extra.update(sparql_calls=0, output_bytes=600_000)
    report = format_report(Collected(results=[run, _metrics("store", 1_000, 1.0)]))
    assert "| 0 | 600 |" in report
    store_row = next(line for line in report.splitlines() if line.startswith("| store"))
    assert store_row.endswith("| - | - |")


def _fake_runner(monkeypatch, wall_of, *, timeout_at=None):
    import subprocess

    from . import runner

    calls = []

    def fake(scenario, triples, *, trace_heap=False, timeout=0):
        calls.append((scenario, triples, trace_heap))
        if triples == timeout_at:
            raise subprocess.TimeoutExpired("x", timeout)
        return _metrics(scenario, triples, wall_of(triples), traced=trace_heap)

    monkeypatch.setattr(runner, "run_scenario", fake)
    return calls


def test_collect_repeats_and_traces_fast_runs(monkeypatch):
    calls = _fake_runner(monkeypatch, lambda n: 0.001 * n)
    collected = collect([1_000], ["export"], repeats=3)
    assert calls == [("export", 1_000, False)] * 3 + [("export", 1_000, True)]
    assert len(collected.results) == 4


def test_collect_skips_sizes_predicted_to_exceed_the_timeout(monkeypatch):
    calls = _fake_runner(monkeypatch, lambda n: n * n / 1e6)
    collected = collect([1_000, 10_000, 100_000], ["import"], timeout=500, slow_s=1e9)
    assert {size for _, size, _ in calls} == {1_000, 10_000}
    assert [s.triples for s in collected.skipped] == [100_000]
    assert "predicted" in collected.skipped[0].reason


def test_collect_skips_larger_sizes_after_a_timeout(monkeypatch):
    calls = _fake_runner(monkeypatch, lambda n: 0.001 * n, timeout_at=10_000)
    collected = collect([1_000, 10_000, 100_000], ["export"], timeout=50)
    assert 100_000 not in {size for _, size, _ in calls}
    assert [s.reason.split(" after")[0] for s in collected.skipped] == ["timed out", "a smaller size timed out"]


def test_collect_does_not_repeat_or_trace_slow_runs(monkeypatch):
    calls = _fake_runner(monkeypatch, lambda n: 100.0)
    collected = collect([1_000], ["import"], repeats=3, slow_s=60)
    assert calls == [("import", 1_000, False)]
    assert "repeats and heap trace skipped" in collected.skipped[0].reason


@pytest.mark.scaling
@pytest.mark.parametrize("scenario", ["export", "store", "import", "rdflib_parse", "rdflib_serialize"])
def test_scenario_scales_roughly_linearly(scenario):
    collected = collect([1_000, 10_000], [scenario])
    assert exponents(collected)[scenario] < 1.5
