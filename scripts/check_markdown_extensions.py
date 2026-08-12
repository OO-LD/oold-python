#!/usr/bin/env python
"""
Guard zensical.toml against Zensical's default Markdown extensions drifting.

Why this exists: a project that declares ANY markdown_extensions REPLACES Zensical's
default set instead of extending it. zensical/config.py reads them via

    config.get("markdown_extensions", DEFAULT_MARKDOWN_EXTENSIONS)

which is a fallback, not a merge, so every default left out of zensical.toml is
silently switched off. There is no warning and no build failure: the extension simply
stops applying, and the damage surfaces as prose that renders wrong. That is how
`!!! note` / `!!! tip` admonitions ended up published as literal text.

zensical.toml therefore restates the upstream defaults verbatim. This script checks
that the restatement is still true against the *installed* Zensical (the "zensical"
dev dependency pinned in pyproject.toml), so bumping that pin cannot quietly change
the effective set. Deliberate deviations are declared below and must each stay
justified.

Usage:
    python scripts/check_markdown_extensions.py

Run via `make check-extensions`, which is also what `make check` and the
`markdown-extensions` pre-commit hook call.
"""

import copy
import os
import sys

try:
    import tomllib  # ty: ignore[unresolved-import]  # stdlib on 3.11+; ty type-checks against the 3.10 floor
except ModuleNotFoundError:
    sys.exit(
        "This check needs Python 3.11+ for the stdlib tomllib parser (the project "
        "itself supports 3.10+, but `make check` and CI both run on 3.12). Use that "
        "interpreter, or a newer one, to run this check directly."
    )

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG = os.path.join(ROOT, "zensical.toml")

# Upstream defaults this project deliberately does NOT enable. Keep the reason with
# the entry; the same reasoning is spelled out next to the commented-out table in
# zensical.toml. Empty for now: pymdownx.smartsymbols was reviewed and kept enabled,
# see zensical.toml.
INTENTIONALLY_DISABLED: dict[str, str] = {}

# Upstream defaults this project enables but configures differently. Their options are
# exempt from the comparison; their presence is not. Empty for now: the mermaid fence's
# explicit "format" and the trimmed pymdownx.tabbed used to differ from the default
# without a stated reason, and neither turned out to be needed, so both were restored
# to match the default instead of being recorded here.
INTENTIONAL_OVERRIDES: dict[str, str] = {}

# Extensions this project adds on top of the defaults. Empty for now.
PROJECT_ADDITIONS: dict[str, str] = {}


def load_converter():
    """Return Zensical's own extension normalizer, so both sides are compared as
    Zensical itself sees them rather than through a reimplementation here."""
    try:
        import zensical.config as zconfig
    except ImportError:
        sys.exit(
            "zensical is not importable.\n"
            "Run `uv sync` (or `make install`) so the pinned dev dependency is "
            "available, then run this via `make check-extensions`."
        )
    missing = [
        n
        for n in ("DEFAULT_MARKDOWN_EXTENSIONS", "_convert_markdown_extensions")
        if not hasattr(zconfig, n)
    ]
    if missing:
        sys.exit(
            f"zensical.config no longer provides: {', '.join(missing)}.\n"
            "The config internals this guard relies on have changed upstream. Re-read\n"
            "zensical/config.py, confirm how markdown_extensions are resolved now, and\n"
            "update this script and the restated block in zensical.toml together."
        )
    return zconfig


def normalize(value):
    """Reduce a config value to something comparable. Upstream stores the emoji hooks
    as function objects while the TOML names them as strings, so callables collapse to
    their dotted path."""
    if callable(value):
        return f"{value.__module__}.{value.__qualname__}"
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def resolve(zconfig, table):
    """Flatten a markdown_extensions table the way Zensical does, into {name: config}."""
    names, configs = zconfig._convert_markdown_extensions(copy.deepcopy(table))
    return {name: normalize(configs.get(name, {})) for name in names}


def main():
    zconfig = load_converter()

    with open(CONFIG, "rb") as fh:
        declared_table = tomllib.load(fh)["project"]["markdown_extensions"]

    declared = resolve(zconfig, declared_table)
    defaults = resolve(zconfig, zconfig.DEFAULT_MARKDOWN_EXTENSIONS)

    problems = []

    for name, reason in sorted(INTENTIONALLY_DISABLED.items()):
        if name not in defaults:
            problems.append(
                f"{name} is listed as deliberately disabled but is no longer a Zensical "
                f"default. Drop it from INTENTIONALLY_DISABLED and from zensical.toml."
            )
        elif name in declared:
            problems.append(
                f"{name} is listed as deliberately disabled ({reason}) but zensical.toml "
                f"enables it. Remove the table or drop the allow-list entry."
            )

    for name in sorted(set(defaults) - set(declared) - set(INTENTIONALLY_DISABLED)):
        problems.append(
            f"{name} is a Zensical default but zensical.toml does not declare it, so it "
            f"is silently switched off. Add [project.markdown_extensions.{name}] to the "
            f"restated defaults block, or record it in INTENTIONALLY_DISABLED with a reason."
        )

    for name in sorted(set(declared) - set(defaults) - set(PROJECT_ADDITIONS)):
        problems.append(
            f"{name} is declared in zensical.toml but is not a Zensical default and is not "
            f"a known project addition. Either Zensical dropped it from its defaults (move "
            f"the table out of the restated block and into PROJECT_ADDITIONS if the docs "
            f"still need it, or delete it), this project chose it without recording it "
            f"(add it to PROJECT_ADDITIONS with a reason), or the name is misspelled and "
            f"the extension is doing nothing."
        )

    for name, reason in sorted(PROJECT_ADDITIONS.items()):
        if name not in declared:
            problems.append(
                f"{name} is listed as a project addition ({reason}) but zensical.toml no "
                f"longer declares it. Drop the PROJECT_ADDITIONS entry."
            )

    for name in sorted(set(declared) & set(defaults)):
        if name in INTENTIONAL_OVERRIDES:
            if declared[name] == defaults[name]:
                problems.append(
                    f"{name} is listed as an intentional override but its options now match "
                    f"the upstream default exactly. Drop the INTENTIONAL_OVERRIDES entry and "
                    f"the explanatory comment in zensical.toml."
                )
            continue
        if declared[name] != defaults[name]:
            problems.append(
                f"{name} options drifted from the upstream default.\n"
                f"    zensical.toml: {declared[name]}\n"
                f"    zensical:      {defaults[name]}\n"
                f"    Restate the upstream value, or record the deviation in "
                f"INTENTIONAL_OVERRIDES with a reason."
            )

    if problems:
        print(
            f"zensical.toml no longer matches Zensical's defaults "
            f"({len(problems)} problem{'s' if len(problems) > 1 else ''}):\n",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  - {problem}\n", file=sys.stderr)
        print(
            "The restated block in zensical.toml exists so the effective extension set is\n"
            "visible in one file. Reconcile it with the installed Zensical before building.",
            file=sys.stderr,
        )
        return 1

    print(
        f"markdown extensions OK ({len(declared)} declared, "
        f"{len(set(declared) & set(defaults))} matching Zensical's defaults, "
        f"{len(INTENTIONALLY_DISABLED)} deliberately disabled, "
        f"{len(PROJECT_ADDITIONS)} project addition(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
