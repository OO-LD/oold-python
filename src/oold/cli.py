"""The ``oold`` command line entry point.

A thin group that currently hosts the validation commands and leaves room for future
non-validation subcommands. The implementation lives in :mod:`oold.validation.cli`, reached
through :func:`main` for ``oold`` and :func:`validate_main` for ``oold-validate``. The second
name matches the command oold-schema itself installs (``npx oold-validate <dir>``), so a script
or CI snippet written against either package keeps working with the other.

Validation needs the ``validation`` extra, so an import failure is reported as an actionable
message rather than a traceback. Both console scripts go through this module for that reason:
binding either one straight at the click command would skip the guard and print a traceback on
an install without the extra.
"""

from __future__ import annotations

import sys

INSTALL_HINT = (
    "The validation commands need extra dependencies.\n"
    '  uv add "oold[validation]"\n'
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


def validate_main() -> None:
    """``oold-validate``, the JS-compatible name for ``oold validate``."""
    try:
        import click  # noqa: F401

        from oold.validation.cli import validate
    except ImportError as exc:  # pragma: no cover - depends on the install
        print(f"oold-validate: {exc}\n\n{INSTALL_HINT}", file=sys.stderr)
        raise SystemExit(2) from exc

    validate()


if __name__ == "__main__":
    main()
