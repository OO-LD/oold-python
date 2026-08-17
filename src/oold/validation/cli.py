"""Command line interface for OO-LD validation.

Exposed twice, from one implementation: as ``oold validate ...`` (see :mod:`oold.cli`) and as
``oold-validate ...``, whose name and directory-argument behaviour match oold-schema's own
``npx oold-validate <dir>`` so documentation and CI snippets carry across between the two
repositories.

Exit code is 0 only when no check failed. Warnings do not fail a run.
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import click

from .meta_store import MetaSchemaError, describe_store, fetch_remote, resolve_selection
from .pipeline import Options, run_compliance, validate_directory, validate_instance, validate_schema
from .report import FAIL, OK, SKIP, WARN, Report

EXIT_OK = 0
EXIT_FAILED = 1

#: Where a rule id resolves in the published specification. The anchor is emitted by
#: oold-schema's spec renderer, so a report can link straight to the requirement it cites.
SPEC_RULE_URL = "https://oo-ld.org/latest/spec/#rule-"

_STATUS_STYLE = {
    OK: {"fg": "green"},
    FAIL: {"fg": "red", "bold": True},
    WARN: {"fg": "yellow"},
    SKIP: {"fg": "cyan"},
}

_meta_option = click.option(
    "--meta",
    "meta",
    multiple=True,
    metavar="VERSION",
    help="Meta-schema version: latest (default), a version such as 0.7.0, remote, or all. "
    "Repeat to validate against several at once.",
)
_offline_option = click.option(
    "--offline", is_flag=True, help="Never fetch over the network; use local files and the cache."
)
_json_option = click.option("--json", "as_json", is_flag=True, help="Print the report as JSON.")
_verbose_option = click.option("--verbose", "-v", is_flag=True, help="Show every check, not only problems.")
_output_option = click.option("--output", type=click.Path(path_type=Path), help="Write the JSON report to this file.")


def _options(meta, offline, **extra) -> Options:
    return Options(meta=tuple(meta) or ("latest",), offline=offline, **extra)


def _emit(report: Report, as_json: bool, verbose: bool, output: Path | None) -> None:
    verbosity = "full" if verbose else "summary"
    if output:
        output.write_text(json.dumps(report.to_dict(verbosity), indent=2, default=str), encoding="utf-8")
    if as_json:
        click.echo(json.dumps(report.to_dict(verbosity), indent=2, default=str))
    else:
        _print_human(report, verbose)


def _print_human(report: Report, verbose: bool) -> None:
    if report.fatal_error:
        click.echo(click.style("ERROR", fg="red", bold=True) + f"  {report.source}")
        click.echo(f"  {report.fatal_error}")
        return

    counts = report.counts
    status = click.style("PASS", fg="green", bold=True) if report.passed else click.style("FAIL", fg="red", bold=True)
    versions = ", ".join(report.meta_versions) or "none"
    click.echo(f"{status}  {report.source}")
    click.echo(f"      meta-schema: {versions}")
    click.echo(
        f"      {counts[OK]} ok, {counts[FAIL]} failed, {counts[WARN]} warning(s), "
        f"{counts[SKIP]} skipped, across {len(report.targets())} target(s)"
    )

    shown = report.checks if verbose else [c for c in report.checks if c.status != OK]
    if shown:
        click.echo()
        for check in shown:
            style = _STATUS_STYLE.get(check.status, {})
            label = click.style(check.status.upper().ljust(4), **style)
            rule = click.style(f" {check.rule}", fg="blue") if check.rule else ""
            version = f" [{check.meta_version}]" if check.meta_version else ""
            message = f": {check.message}" if check.message else ""
            click.echo(f"  {label}{rule} {check.id:<22} {check.target}{version}{message}")
            if check.rule and verbose:
                click.echo(f"       {SPEC_RULE_URL}{check.rule}")

    for note in report.notes[1:] if report.notes else []:
        click.echo(f"  note: {note}")

    if not verbose and counts[OK]:
        click.echo()
        click.echo(f"  ({counts[OK]} passing check(s) hidden; use --verbose to see them)")


def _run(report: Report, as_json: bool, verbose: bool, output: Path | None) -> None:
    _emit(report, as_json, verbose, output)
    sys.exit(EXIT_OK if report.passed else EXIT_FAILED)


# ---------------------------------------------------------------------------- commands


@click.command("validate")
@click.argument("target", type=click.Path(exists=True, path_type=Path))
@_meta_option
@_offline_option
@_json_option
@_verbose_option
@_output_option
def validate(target: Path, meta, offline: bool, as_json: bool, verbose: bool, output: Path | None):
    """Validate an OO-LD schema, or every schema and instance in a directory.

    TARGET is a *.schema.json file or a directory. A directory runs the same general-workflow
    checks over every schema and instance it contains.
    """
    try:
        options = _options(meta, offline)
    except MetaSchemaError as exc:
        raise click.ClickException(str(exc)) from exc

    report = validate_directory(target, options) if target.is_dir() else validate_schema(target, options)
    _run(report, as_json, verbose, output)


@click.command("validate-instance")
@click.argument("instance", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--schema",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Validate against this schema instead of the one named by $schema.",
)
@_meta_option
@_offline_option
@_json_option
@_verbose_option
@_output_option
def validate_instance_command(
    instance: Path,
    schema: Path | None,
    meta,
    offline: bool,
    as_json: bool,
    verbose: bool,
    output: Path | None,
):
    """Validate an instance document against the schema it names.

    The instance names its schema with $schema, resolved relative to the instance itself.
    """
    report = validate_instance(instance, schema, _options(meta, offline))
    _run(report, as_json, verbose, output)


@click.command("compliance")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
@_meta_option
@_offline_option
@_json_option
@_verbose_option
@_output_option
def compliance_command(directory: Path, meta, offline: bool, as_json: bool, verbose: bool, output: Path | None):
    """Run a deterministic compliance suite, plus the vocabulary-coverage cross-check.

    DIRECTORY holds the fixture files, for example oold-schema's examples/compliance.
    """
    report = run_compliance(directory, _options(meta, offline))
    _run(report, as_json, verbose, output)


@click.group("meta")
def meta_group() -> None:
    """Inspect and refresh the meta-schema store."""


@meta_group.command("list")
@_json_option
def meta_list(as_json: bool) -> None:
    """Show tracked meta-schema versions and the state of the remote cache."""
    store = describe_store()
    if as_json:
        click.echo(json.dumps(store, indent=2))
        return

    click.echo(f"tracked versions ({store['tracked_dir']}):")
    for entry in store["versions"]:
        marker = " (latest)" if entry["version"] == store["latest"] else ""
        tag = entry.get("tag", "?")
        added = entry.get("added", "?")
        click.echo(f"  {entry['version']}{marker}  from {tag}, added {added}")
    if not store["versions"]:
        click.echo("  none; see the README in that directory")

    remote = store["remote"]
    click.echo()
    click.echo(f"remote ({remote['base_url']}):")
    state = f"cached, fetched {remote['fetched']}" if remote["cached"] else "not cached"
    click.echo(f"  {state}")
    click.echo(f"  cache dir: {remote['cache_dir']}")


@meta_group.command("fetch")
@click.option("--force", is_flag=True, help="Refetch even when a cached copy exists.")
def meta_fetch(force: bool) -> None:
    """Fetch the unreleased meta-schemas from the oold-schema repository into the cache.

    This never writes into the tracked version history, so a released version cannot change
    meaning behind your back.
    """
    try:
        target = fetch_remote(force=force)
    except MetaSchemaError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"fetched into {target}")


@click.group("rules")
def rules_group() -> None:
    """Look up the normative rules the validator cites."""


@rules_group.command("list")
@_meta_option
@_offline_option
@click.option("--area", help="Only rules in this area, e.g. RT, CMP, INS.")
@click.option(
    "--unchecked",
    is_flag=True,
    help="Only machine-checkable rules that no check enforces yet, which is the coverage gap.",
)
@_json_option
def rules_list(meta, offline: bool, area: str | None, unchecked: bool, as_json: bool) -> None:
    """List the rules in the specification's catalog."""
    from .check_registry import rule_map

    bundle = _rules_bundle(meta, offline)
    rules = bundle.rules
    if area:
        rules = [r for r in rules if r["area"].upper() == area.upper()]
    if unchecked:
        enforced = set(rule_map().values())
        rules = [r for r in bundle.machine_checkable_rules() if r["id"] not in enforced]

    if as_json:
        click.echo(json.dumps(rules, indent=2))
        return
    if not rules:
        click.echo("no rules match")
        return

    enforced_by = {v: k for k, v in rule_map().items()}
    for rule in rules:
        flag = "!" if rule.get("deprecated") else " "
        check = enforced_by.get(rule["id"], "-")
        click.echo(
            f"{flag}{click.style(rule['id'], fg='blue')}  {rule['level']:<10} "
            f"{rule['applies_to']:<14} {check:<20} {rule['summary']}"
        )
    click.echo()
    click.echo(f"  {len(rules)} rule(s); the column before the summary is the check that enforces each")


@rules_group.command("explain")
@click.argument("rule_id")
@_meta_option
@_offline_option
@_json_option
def rules_explain(rule_id: str, meta, offline: bool, as_json: bool) -> None:
    """Show one rule in full: its level, what it binds, and the specification text."""
    from .check_registry import rule_map

    bundle = _rules_bundle(meta, offline)
    # Case-insensitive by comparing both sides upper, rather than upper-casing rule_id alone:
    # ids now mint a lowercase hex suffix (OOLD-RT-08f2), so `.upper()` on the query alone would
    # no longer match the catalogue's own casing.
    rule = next((r for r in bundle.rules if r["id"].upper() == rule_id.upper()), None)
    if rule is None:
        raise click.ClickException(
            f"{rule_id} is not in the catalog for meta-schema {bundle.version}. "
            "Try `oold rules list` to see what is available."
        )
    if as_json:
        click.echo(json.dumps(rule, indent=2))
        return

    enforced_by = {v: k for k, v in rule_map().items()}
    click.echo(click.style(rule["id"], fg="blue", bold=True) + f"  {rule['level']}")
    click.echo(f"  {rule['summary']}")
    click.echo()
    click.echo(f"  area       {rule['area']}")
    click.echo(f"  applies to {rule['applies_to']}")
    click.echo(
        f"  machine-checkable  {rule['machine_checkable']}"
        + (f" (enforced by {enforced_by[rule['id']]})" if rule["id"] in enforced_by else "")
    )
    click.echo(f"  since      {rule['since']}")
    if rule.get("deprecated"):
        click.echo(
            f"  {click.style('DEPRECATED', fg='yellow')} superseded by {', '.join(rule.get('superseded_by', [])) or 'nothing'}"
        )
    click.echo(f"  spec       {SPEC_RULE_URL}{rule['id']}")
    click.echo()
    click.echo(click.style("  specification text:", bold=True))
    click.echo(click.wrap_text(rule["text"], width=94, initial_indent="    ", subsequent_indent="    "))


def _rules_bundle(meta, offline: bool):
    """The first selected bundle that actually ships a catalog."""
    try:
        bundles = resolve_selection(tuple(meta) or ("latest",), offline=offline)
    except MetaSchemaError as exc:
        raise click.ClickException(str(exc)) from exc
    for bundle in bundles:
        if bundle.has_rules:
            return bundle
    names = ", ".join(b.version for b in bundles)
    raise click.ClickException(
        f"meta-schema version(s) {names} ship no rule catalog. It was introduced upstream after "
        "0.8.0, so try `--meta remote` once oold-schema has published it."
    )


@click.group("checks")
def checks_group() -> None:
    """Look up the checks this validator can run.

    Check ids (``lint.container``, ``rule.id-fragment``) name which check produced a finding;
    rule ids (``OOLD-RT-08f2``, see ``oold rules``) name the specification requirement it
    enforces, when it enforces one at all. The two are not peers: see
    ``docs/architecture.md``, "Validation subsystem design", for why.
    """


@checks_group.command("list")
@click.option("--prefix", help="Only checks whose id starts with this, e.g. lint.")
@click.option(
    "--unmapped",
    is_flag=True,
    help="Only checks that enforce no specification rule, the mirror of `oold rules list --unchecked`.",
)
@_json_option
def checks_list(prefix: str | None, unmapped: bool, as_json: bool) -> None:
    """List the checks this validator can run."""
    from .check_registry import CHECKS

    checks = CHECKS
    if prefix:
        checks = [c for c in checks if c.id.startswith(prefix)]
    if unmapped:
        checks = [c for c in checks if not c.rule]

    if as_json:
        click.echo(json.dumps([_check_summary(c) for c in checks], indent=2))
        return
    if not checks:
        click.echo("no checks match")
        return

    for check in checks:
        rule = check.rule or "-"
        # The id is padded before styling: ANSI escape codes count towards an f-string field
        # width, so padding a styled string misaligns the columns that follow it.
        click.echo(
            f"{click.style(check.id.ljust(24), fg='blue')} {check.default_status.upper():<6} {rule:<16} {check.summary}"
        )
    click.echo()
    click.echo(f"  {len(checks)} check(s); the column before the summary is the rule each enforces, if any")


@checks_group.command("explain")
@click.argument("check_id")
@_json_option
def checks_explain(check_id: str, as_json: bool) -> None:
    """Show one check in full: what it verifies, the rule it enforces, and where it is detected."""
    from .check_registry import info

    check = info(check_id)
    if check is None:
        raise click.ClickException(
            f"{check_id} is not a registered check. Try `oold checks list` to see what is available."
        )

    if as_json:
        click.echo(json.dumps(_check_summary(check, full=True), indent=2))
        return

    click.echo(click.style(check.id, fg="blue", bold=True) + f"  {check.default_status.upper()} by default")
    click.echo(f"  {check.summary}")
    click.echo()
    if check.rule:
        click.echo(f"  rule       {check.rule}   ({_rule_version_summary(check.rule)})")
    else:
        click.echo("  rule       none; this check enforces no single specification requirement")
    click.echo(f"  detected   {_detection_site(check)}")
    click.echo(f"  per version {'yes' if check.per_version else 'no'}")


def _check_summary(check, full: bool = False) -> dict:
    payload = {
        "id": check.id,
        "summary": check.summary,
        "rule": check.rule,
        "default_status": check.default_status,
        "per_version": check.per_version,
        "predates_catalog": check.predates_catalog,
    }
    if full:
        payload["detection_site"] = _detection_site(check)
        if check.rule:
            payload["rule_versions"] = _rule_version_summary(check.rule)
    return payload


def _detection_site(check) -> str:
    """Where ``check``'s verdict is decided, derived from ``detects``/``run`` with `inspect`.

    Never the emitting site: that is what names the check id and reports the finding, which is
    findable by grepping the id and would otherwise be a second, unmaintained field to keep in
    step.
    """
    fn = check.detects or check.run
    if fn is None:
        return "no single detection site; see the check's own module for its implementation"
    module = (getattr(fn, "__module__", "") or "").rsplit(".", 1)[-1]
    qualname = getattr(fn, "__qualname__", getattr(fn, "__name__", repr(fn)))
    label = f"{module}.{qualname}" if module else qualname
    try:
        source_file = Path(inspect.getsourcefile(fn) or inspect.getfile(fn)).name
        _, lineno = inspect.getsourcelines(fn)
    except (OSError, TypeError):
        return label
    return f"{label}   ({source_file}:{lineno})"


def _rule_version_summary(rule_id: str) -> str:
    """Which tracked meta-schema versions state ``rule_id``, and which do not."""
    from .meta_store import load_tracked, tracked_versions

    stated, absent = [], []
    for version in tracked_versions():
        bundle = load_tracked(version)
        (stated if bundle.rule(rule_id) else absent).append(version)

    parts = []
    if stated:
        parts.append(f"stated by {', '.join(stated)}")
    if absent:
        parts.append(f"absent from {', '.join(absent)}")
    return "; ".join(parts) if parts else "not found in any tracked version"


@click.group()
@click.version_option(package_name="oold")
def main() -> None:
    """Validate OO-LD schemas and instance documents."""


main.add_command(validate)
main.add_command(validate_instance_command)
main.add_command(compliance_command)
main.add_command(meta_group)
main.add_command(rules_group)
main.add_command(checks_group)


if __name__ == "__main__":
    main()
