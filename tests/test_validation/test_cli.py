"""The CLI surface, including exit codes so it works as a CI gate."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from oold.validation.cli import main


@pytest.fixture
def run():
    runner = CliRunner()

    def invoke(*args):
        return runner.invoke(main, [*args], catch_exceptions=False)

    return invoke


def test_a_valid_directory_exits_zero(run, data_dir):
    result = run("validate", str(data_dir), "--offline")
    assert result.exit_code == 0, result.output
    assert "PASS" in result.output


def test_a_broken_schema_exits_nonzero(run, broken_dir):
    result = run("validate", str(broken_dir / "undefined_prefix.schema.json"), "--offline")
    assert result.exit_code == 1
    assert "FAIL" in result.output
    assert "context.predicates" in result.output


def test_failures_are_shown_by_default_and_passes_are_not(run, data_dir):
    result = run("validate", str(data_dir), "--offline")
    assert "hidden" in result.output
    assert "OK   schema.meta" not in result.output


def test_verbose_shows_every_check(run, data_dir):
    result = run("validate", str(data_dir / "Thing.schema.json"), "--offline", "--verbose")
    assert "schema.meta" in result.output
    assert "context.predicates" in result.output


def test_json_output_is_machine_readable(run, data_dir):
    result = run("validate", str(data_dir / "Thing.schema.json"), "--offline", "--json")
    payload = json.loads(result.output)
    assert payload["passed"] is True
    assert payload["summary"]["ok"] > 0


def test_output_file_is_written(run, data_dir, tmp_path):
    target = tmp_path / "report.json"
    run("validate", str(data_dir / "Thing.schema.json"), "--offline", "--output", str(target))
    assert json.loads(target.read_text(encoding="utf-8"))["passed"] is True


def test_validate_instance_command(run, data_dir):
    result = run("validate-instance", str(data_dir / "RdfPerson.instance.json"), "--offline")
    assert result.exit_code == 0
    assert "PASS" in result.output


def test_validate_instance_with_an_explicit_schema(run, data_dir):
    result = run(
        "validate-instance",
        str(data_dir / "RdfPerson.instance.json"),
        "--schema",
        str(data_dir / "RdfPerson.schema.json"),
        "--offline",
    )
    assert result.exit_code == 0


def test_an_explicit_schema_elsewhere_is_refused_with_a_reason(run, data_dir, tmp_path):
    """Relative @context references only resolve from the instance's own directory."""
    stray = tmp_path / "Other.schema.json"
    stray.write_text('{"type": "object"}', encoding="utf-8")
    result = run(
        "validate-instance",
        str(data_dir / "RdfPerson.instance.json"),
        "--schema",
        str(stray),
        "--offline",
    )
    assert result.exit_code == 1
    assert "same directory" in result.output


def test_compliance_command(run, compliance_dir):
    result = run("compliance", str(compliance_dir), "--offline", "--json")
    payload = json.loads(result.output)
    assert payload["summary"]["checks"] > 60


def test_meta_list_shows_versions_and_cache_state(run, isolated_cache):
    result = run("meta", "list")
    assert result.exit_code == 0
    assert "tracked versions" in result.output
    assert "(latest)" in result.output
    assert "not cached" in result.output


def test_meta_list_json(run):
    payload = json.loads(run("meta", "list", "--json").output)
    assert payload["latest"]
    assert payload["versions"]


def test_unknown_meta_version_reports_cleanly(run, data_dir):
    result = run("validate", str(data_dir), "--meta", "9.9.9", "--offline")
    assert result.exit_code == 1
    assert "ERROR" in result.output
    assert "not tracked" in result.output


def test_meta_version_is_shown_in_the_report(run, data_dir):
    result = run("validate", str(data_dir / "Thing.schema.json"), "--offline")
    assert "meta-schema:" in result.output


def test_a_missing_target_is_rejected_by_the_argument_parser(run):
    runner = CliRunner()
    result = runner.invoke(main, ["validate", "no-such-path"])
    assert result.exit_code != 0


def test_validate_detects_an_instance_file(run, data_dir):
    result = run("validate", str(data_dir / "PersonWithPet.instance.json"), "--offline", "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    ids = {check["id"] for check in payload["checks"]}
    assert "instance.schema" in ids
    assert "roundtrip.instance" in ids


def test_validate_detects_a_schema_file(run, data_dir):
    result = run("validate", str(data_dir / "PersonWithPet.schema.json"), "--offline", "--verbose")
    assert "schema.meta" in result.output


def test_as_instance_overrides_detection_on_a_schema_file(run, data_dir):
    result = run("validate", str(data_dir / "PersonWithPet.schema.json"), "--as-instance", "--offline", "--json")
    payload = json.loads(result.output)
    ids = {check["id"] for check in payload["checks"]}
    assert "instance.schema" in ids
    assert "schema.meta" not in ids


def test_as_schema_overrides_detection_on_an_instance_file(run, data_dir):
    result = run("validate", str(data_dir / "PersonWithPet.instance.json"), "--as-schema", "--offline", "--json")
    payload = json.loads(result.output)
    ids = {check["id"] for check in payload["checks"]}
    assert "schema.meta" in ids
    assert "instance.schema" not in ids


def test_a_legacy_dialect_is_still_classified_as_a_schema(run, broken_dir):
    result = run("validate", str(broken_dir / "legacy_dialect.schema.json"), "--offline", "--verbose")
    assert "schema.meta" in result.output or "rule.dialect-version" in result.output


def test_a_file_with_no_schema_key_is_rejected(run, tmp_path):
    target = tmp_path / "no_schema.json"
    target.write_text('{"foo": "bar"}', encoding="utf-8")
    result = run("validate", str(target), "--offline")
    assert result.exit_code != 0
    assert "--as-schema" in result.output


def test_as_schema_with_a_directory_is_rejected(run, data_dir):
    result = run("validate", str(data_dir), "--as-schema", "--offline")
    assert result.exit_code != 0


def test_as_schema_and_as_instance_together_are_rejected(run, data_dir):
    result = run(
        "validate",
        str(data_dir / "PersonWithPet.schema.json"),
        "--as-schema",
        "--as-instance",
        "--offline",
    )
    assert result.exit_code != 0


# ------------------------------------------------------------------ console scripts


def test_both_console_scripts_keep_the_missing_extra_guard():
    """Binding either script straight at a click command skips oold.cli's ImportError guard.

    Without the extra installed that turns an actionable install hint into a traceback, and
    nothing else would notice, since the test suite always has the extra.
    """
    from importlib.metadata import distribution

    # The installed metadata rather than pyproject.toml: it is what actually gets written into
    # the console scripts, and reading it needs no TOML parser on Python 3.10.
    scripts = {ep.name: ep.value for ep in distribution("oold").entry_points if ep.group == "console_scripts"}

    assert set(scripts) == {"oold", "oold-validate"}
    for name, target in scripts.items():
        assert target.startswith("oold.cli:"), f"{name} bypasses the guard in oold.cli: {target}"
