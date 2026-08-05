"""Command line interface for OO-LD validation.

Exposed twice, from one implementation: as ``oold validate ...`` (see :mod:`oold.cli`) and as
``oold-validate ...``, whose name and directory-argument behaviour match the reference
harness's ``npx oold-validate <dir>`` so documentation and CI snippets carry across between the
two repositories.

Exit code is 0 only when no check failed. Warnings do not fail a run, matching the reference.
"""

from __future__ import annotations

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
    tier as `oold-validate <dir>` in the reference harness.
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
    help="Only checkable rules that no check enforces yet, which is the coverage gap.",
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
        rules = [r for r in bundle.checkable_rules() if r["id"] not in enforced]

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
    rule = bundle.rule(rule_id.upper())
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
        f"  checkable  {rule['checkable']}"
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


@click.group()
@click.version_option(package_name="oold")
def main() -> None:
    """Validate OO-LD schemas and instance documents."""


main.add_command(validate)
main.add_command(validate_instance_command)
main.add_command(compliance_command)
main.add_command(meta_group)
main.add_command(rules_group)


if __name__ == "__main__":
    main()
