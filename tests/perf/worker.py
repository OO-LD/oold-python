"""Runs one scenario in this process and prints its Metrics as JSON on the last line."""

import argparse
import json

from .harness import measure
from .scenarios import SCENARIOS


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=sorted(SCENARIOS))
    parser.add_argument("triples", type=int)
    parser.add_argument("--trace-heap", action="store_true")
    args = parser.parse_args(argv)

    prepared = SCENARIOS[args.scenario](args.triples)
    metrics = measure(
        args.scenario,
        prepared.run,
        args.triples,
        trace_heap=args.trace_heap,
        latency_samples=lambda: prepared.samples,
    )
    if not args.trace_heap:
        prepared.verify()
    print(json.dumps(metrics.to_dict()))


if __name__ == "__main__":
    main()
