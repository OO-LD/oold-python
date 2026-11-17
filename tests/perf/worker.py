"""Runs one scenario in this process and prints its Metrics as JSON on the last line."""

import argparse
import cProfile
import json
import pstats

from rdflib import Graph

from .harness import count_calls, measure
from .scenarios import SCENARIOS


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=sorted(SCENARIOS))
    parser.add_argument("triples", type=int)
    parser.add_argument("--trace-heap", action="store_true")
    parser.add_argument(
        "--profile", type=int, metavar="TOP", help="print the TOP cumulative-time functions instead of metrics"
    )
    args = parser.parse_args(argv)

    prepared = SCENARIOS[args.scenario](args.triples)
    if args.profile:
        profiler = cProfile.Profile()
        profiler.runcall(prepared.run)
        pstats.Stats(profiler).sort_stats("cumulative").print_stats(args.profile)
        return
    with count_calls([(Graph, "query"), (Graph, "update")]) as sparql:
        metrics = measure(
            args.scenario,
            prepared.run,
            args.triples,
            trace_heap=args.trace_heap,
            latency_samples=lambda: prepared.samples,
        )
    metrics.extra["sparql_calls"] = sparql.count
    if prepared.output_bytes:
        metrics.extra["output_bytes"] = prepared.output_bytes()
    if not args.trace_heap:
        prepared.verify()
    print(json.dumps(metrics.to_dict()))


if __name__ == "__main__":
    main()
