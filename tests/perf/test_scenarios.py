import json

import pytest

from .dataset import TRIPLE_SIZES
from .harness import dump
from .runner import collect, run_scenario
from .scenarios import SCENARIOS

SMOKE_TRIPLES = TRIPLE_SIZES[0]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_scenario_is_correct_in_process(scenario):
    prepared = SCENARIOS[scenario](200)
    prepared.run()
    prepared.verify()


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_verify_fails_when_nothing_ran(scenario):
    with pytest.raises(AssertionError):
        SCENARIOS[scenario](200).verify()


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_scenario_runs_in_a_subprocess_at_1k(scenario):
    result = run_scenario(scenario, SMOKE_TRIPLES)
    assert result.scenario == scenario
    assert result.triples == SMOKE_TRIPLES
    assert not result.traced
    assert result.wall_s > 0
    assert result.rss_peak_bytes >= result.rss_start_bytes
    assert result.throughput > 0


def test_traced_pass_reports_the_heap_peak():
    result = run_scenario("export", 200, trace_heap=True)
    assert result.traced
    assert result.heap_peak_bytes > 0


def test_a_failing_scenario_surfaces_its_error():
    with pytest.raises(RuntimeError, match="failed"):
        run_scenario("export", 5)


def test_collect_writes_one_entry_per_scenario_and_size(tmp_path):
    collected = collect([200], ["export", "store"])
    path = tmp_path / "result.json"
    dump(collected.results, path)
    benchmarks = json.loads(path.read_text())["benchmarks"]
    assert [b["name"] for b in benchmarks] == ["export[200]", "store[200]"]
    assert all(b["extra_info"]["heap_peak_bytes"] > 0 for b in benchmarks)


def test_worker_profile_prints_the_hot_functions(capsys):
    from .worker import main

    main(["export", "200", "--profile", "5"])
    assert "cumulative" in capsys.readouterr().out
