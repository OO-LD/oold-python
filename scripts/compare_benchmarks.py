#!/usr/bin/env python
"""
Compare pytest-benchmark results between baseline and current run.
Use in CI/CD to detect performance regressions.

Usage:
    python scripts/compare_benchmarks.py baseline.json current.json --threshold 1.5
"""

import json
import sys
from typing import Dict, List, Tuple


def load_benchmark_data(filepath: str) -> Dict:
    """Load benchmark JSON data."""
    with open(filepath) as f:
        return json.load(f)


def extract_benchmarks(data: Dict) -> Dict[str, Dict]:
    """Extract benchmark results by test name."""
    benchmarks = {}
    for bench in data.get("benchmarks", []):
        name = bench["name"]
        stats = bench["stats"]
        benchmarks[name] = {
            "mean": stats["mean"],
            "median": stats["median"],
            "stddev": stats["stddev"],
            "min": stats["min"],
            "max": stats["max"],
        }
    return benchmarks


def compare_benchmarks(
    baseline: Dict[str, Dict], current: Dict[str, Dict], threshold: float = 1.5
) -> Tuple[List[str], List[str], List[str]]:
    """
    Compare benchmark results.

    Returns:
        (regressions, improvements, unchanged)
    """
    regressions = []
    improvements = []
    unchanged = []

    for name in current.keys():
        if name not in baseline:
            print(f"⚠️  New benchmark: {name}")
            continue

        baseline_mean = baseline[name]["mean"]
        current_mean = current[name]["mean"]
        ratio = current_mean / baseline_mean

        change_pct = (ratio - 1.0) * 100

        if ratio > threshold:
            regressions.append(
                f"❌ {name}: {baseline_mean:.4f}s → {current_mean:.4f}s "
                f"({change_pct:+.1f}%, ratio: {ratio:.2f}x)"
            )
        elif ratio < (1.0 / threshold):
            improvements.append(
                f"✅ {name}: {baseline_mean:.4f}s → {current_mean:.4f}s "
                f"({change_pct:+.1f}%, ratio: {ratio:.2f}x)"
            )
        else:
            unchanged.append(
                f"➖ {name}: {baseline_mean:.4f}s → {current_mean:.4f}s "
                f"({change_pct:+.1f}%)"
            )

    # Check for removed benchmarks
    for name in baseline.keys():
        if name not in current:
            print(f"⚠️  Removed benchmark: {name}")

    return regressions, improvements, unchanged


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Compare pytest-benchmark results")
    parser.add_argument(
        "baseline", type=str, help="Baseline benchmark results JSON file"
    )
    parser.add_argument("current", type=str, help="Current benchmark results JSON file")
    parser.add_argument(
        "--threshold",
        type=float,
        default=1.5,
        help="Regression threshold multiplier (default: 1.5 = 50%% slower)",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit with error code if regressions detected",
    )

    args = parser.parse_args()

    # Load data
    print(f"Loading baseline: {args.baseline}")
    baseline_data = load_benchmark_data(args.baseline)
    baseline_benchmarks = extract_benchmarks(baseline_data)

    print(f"Loading current: {args.current}")
    current_data = load_benchmark_data(args.current)
    current_benchmarks = extract_benchmarks(current_data)

    # Compare
    print(f"\n📊 Comparison (threshold: {args.threshold}x)\n")
    regressions, improvements, unchanged = compare_benchmarks(
        baseline_benchmarks, current_benchmarks, args.threshold
    )

    # Print results
    if regressions:
        print("Performance Regressions:")
        for msg in regressions:
            print(f"  {msg}")
        print()

    if improvements:
        print("Performance Improvements:")
        for msg in improvements:
            print(f"  {msg}")
        print()

    if unchanged:
        print("Unchanged (within threshold):")
        for msg in unchanged:
            print(f"  {msg}")
        print()

    # Summary
    print(
        f"Summary: {len(regressions)} regressions, "
        f"{len(improvements)} improvements, "
        f"{len(unchanged)} unchanged"
    )

    # Exit with error if regressions found
    if args.fail_on_regression and regressions:
        print("\n❌ Performance regressions detected!")
        sys.exit(1)
    else:
        print("\n✅ No significant performance regressions")
        sys.exit(0)


if __name__ == "__main__":
    main()
