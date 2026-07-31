"""The ``oold`` command line entry point.

A thin group that currently hosts the validation commands and leaves room for future
non-validation subcommands. The implementation lives in :mod:`oold.validation.cli`, which is
also bound directly to ``oold-validate`` for compatibility with the reference harness's
``npx oold-validate <dir>``.

Validation needs the ``validation`` extra, so an import failure is reported as an actionable
message rather than a traceback.
"""

from __future__ import annotations

import sys

INSTALL_HINT = (
    "The validation commands need extra dependencies.\n"
    '  pip install "oold[validation]"\n'
    "  uv sync --all-extras     (in a checkout of this repository)"
)


def main() -> None:
    try:
        import click  # noqa: F401

        from oold.validation.cli import main as validation_main
    except ImportError as exc:  # pragma: no cover - depends on the install
        print(f"oold: {exc}\n\n{INSTALL_HINT}", file=sys.stderr)
        raise SystemExit(2) from exc

    validation_main()


if __name__ == "__main__":
    main()
