"""The MCP server: tools are registered, delegate to the pipeline, and never raise."""

from __future__ import annotations

import asyncio
import json

import pytest

mcp_server = pytest.importorskip("oold.validation.mcp_server", reason="the mcp extra is not installed")


def list_tools():
    """Drive the async listing directly, so the suite needs no async pytest plugin."""
    return asyncio.run(mcp_server.mcp.list_tools())


EXPECTED_TOOLS = {
    "validate_oold_schema",
    "validate_oold_instance",
    "validate_oold_directory",
    "run_oold_compliance",
    "generate_oold_instance",
    "check_context_mapping",
    "list_meta_versions",
    "list_oold_rules",
    "list_oold_checks",
}


def test_all_tools_are_registered():
    assert {tool.name for tool in list_tools()} == EXPECTED_TOOLS


def test_every_tool_documents_itself():
    """The description is the whole interface an agent sees."""
    for tool in list_tools():
        assert tool.description and len(tool.description) > 40, tool.name


def test_validate_schema_tool(data_dir):
    result = mcp_server.validate_oold_schema(str(data_dir / "Thing.schema.json"), offline=True)
    assert result.passed is True
    assert result.problems == []


def test_validate_schema_tool_reports_problems_as_data(broken_dir):
    result = mcp_server.validate_oold_schema(str(broken_dir / "undefined_prefix.schema.json"), offline=True)
    assert result.passed is False
    assert any("not an absolute IRI" in p for p in result.problems)


def test_validate_schema_tool_accepts_raw_json():
    schema = json.dumps({
        "$id": "Inline.schema.json",
        "@context": {"ex": "https://example.org/", "name": "ex:name"},
        "type": "object",
        "properties": {"name": {"type": "string"}},
    })
    assert mcp_server.validate_oold_schema(schema, offline=True).passed is True


def test_instance_tool(data_dir):
    result = mcp_server.validate_oold_instance(str(data_dir / "PersonWithPet.instance.json"), offline=True)
    assert result.passed is True


def test_instance_tool_accepts_raw_json_for_instance_and_schema():
    schema = json.dumps({
        "$id": "Inline.schema.json",
        "@context": {"ex": "https://example.org/", "name": "ex:name"},
        "type": "object",
        "properties": {"name": {"type": "string"}},
    })
    instance = json.dumps({"@context": "Inline.schema.json", "name": "Ada"})
    result = mcp_server.validate_oold_instance(instance, schema=schema, offline=True)
    assert result.passed is True
    assert result.problems == []


def test_directory_tool(data_dir):
    result = mcp_server.validate_oold_directory(str(data_dir), offline=True)
    assert result.passed is True
    assert result.summary.targets > 10


def test_generate_tool(data_dir):
    result = mcp_server.generate_oold_instance(str(data_dir / "PersonWithPet.schema.json"))
    assert result.ok is True
    assert result.instance["name"]


def test_generate_tool_reports_a_missing_file_as_data(tmp_path):
    result = mcp_server.generate_oold_instance(str(tmp_path / "nope.schema.json"))
    assert result.ok is False
    assert "not found" in result.error


def test_context_mapping_tool_finds_a_suspicious_predicate():
    document = json.dumps({"@context": {"latitude": "schema:latitude"}, "latitude": 51.5})
    result = mcp_server.check_context_mapping(document)
    assert result.suspicious == {"latitude": "schema:latitude"}


def test_context_mapping_tool_requires_a_context():
    assert mcp_server.check_context_mapping(json.dumps({"a": 1})).ok is False


def test_context_mapping_tool_accepts_raw_json_for_context():
    document = json.dumps({"latitude": 51.5})
    context = json.dumps({"latitude": "https://schema.org/latitude"})
    result = mcp_server.check_context_mapping(document, context)
    assert result.mapped == {"latitude": "https://schema.org/latitude"}


def test_context_mapping_tool_accepts_a_context_path(tmp_path):
    context_file = tmp_path / "context.json"
    context_file.write_text(json.dumps({"latitude": "https://schema.org/latitude"}), encoding="utf-8")
    document = json.dumps({"latitude": 51.5})
    result = mcp_server.check_context_mapping(document, str(context_file))
    assert result.mapped == {"latitude": "https://schema.org/latitude"}


def test_list_meta_versions_tool():
    result = mcp_server.list_meta_versions()
    assert result.latest
    assert result.versions


def test_unknown_meta_version_is_returned_as_data(data_dir):
    """A caller asking about a broken setup wants the explanation, not an exception."""
    result = mcp_server.validate_oold_schema(str(data_dir / "Thing.schema.json"), meta=["9.9.9"], offline=True)
    assert result.passed is False
    assert "not tracked" in result.fatal_error
