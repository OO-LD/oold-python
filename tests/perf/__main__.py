"""``python -m perf``: run the scenarios over several sizes, print a report, write JSON."""

import argparse
import sys

from .dataset import TRIPLE_SIZES
from .harness import dump
from .report import format_report
from .runner import DEFAULT_TIMEOUT_S, SLOW_RUN_S, collect
from .scenarios import SCENARIOS


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m perf")
    parser.add_argument("--sizes", type=int, nargs="+", default=list(TRIPLE_SIZES))
    parser.add_argument("--scenarios", nargs="+", choices=sorted(SCENARIOS), default=list(SCENARIOS))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="seconds per run")
    parser.add_argument(
        "--slow", type=float, default=SLOW_RUN_S, help="runs slower than this are not repeated or traced"
    )
    parser.add_argument("--out", default="benchmark_rdf_results.json")
    args = parser.parse_args(argv)

    collected = collect(
        args.sizes,
        args.scenarios,
        repeats=args.repeats,
        timeout=args.timeout,
        slow_s=args.slow,
        progress=lambda message: print(message, file=sys.stderr, flush=True),
    )
    dump(collected.results, args.out, [s.as_tuple() for s in collected.skipped])
    print(format_report(collected))
    print(f"\nwrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
