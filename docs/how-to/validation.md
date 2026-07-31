# Validation

`oold` can check that an OO-LD schema is well formed and that an instance document conforms to
the schema it names. It is a native Python port of the reference harness in
[oold-schema](https://github.com/OO-LD/oold-schema) (`scripts/validate.mjs`), so the two agree on
verdicts, and it is available three ways: as a library, as a CLI, and as an MCP server.

Install the extra:

```bash
pip install "oold[validation]"      # CLI and library
pip install "oold[validation,mcp]"  # plus the MCP server
```

## Why more than JSON Schema

A property declared in `properties` but missing from `@context` is not a JSON Schema error and
not a JSON-LD error. It simply produces no RDF, and the data quietly loses meaning. There are two
distinct failure modes and only looking for the first misses the worse half:

| Mode | What happens | Reported as |
|---|---|---|
| **Dropped** | The term has no `@context` definition, so the key vanishes on expansion. | `context.predicates`, `roundtrip.generated` |
| **Suspicious** | The term maps through a prefix that was never defined. JSON-LD reads `schema:latitude` as an absolute IRI whose scheme is literally `schema`, so the key survives, the round-trip is clean, and the predicate means nothing. | `context.predicates` |

The second is the dangerous one, because nothing about the output looks wrong.

## CLI

```bash
oold validate path/to/Schema.schema.json     # one schema
oold validate path/to/schemas/               # every schema and instance in a directory
oold validate-instance doc.instance.json     # a document against the schema it names
oold compliance path/to/compliance/          # a deterministic fixture suite
oold meta list                               # tracked meta-schema versions
oold meta fetch                              # refresh the unreleased ones into the cache
```

`oold-validate <dir>` is an alias for `oold validate <dir>`, matching the reference harness's
`npx --yes github:OO-LD/oold-schema oold-validate <dir>` so CI snippets carry across.

Exit code is 0 only when no check failed. Warnings do not fail a run.

### Options

| Option | Meaning |
|---|---|
| `--meta VERSION` | `latest` (default), a version such as `0.8.0`, `remote`, or `all`. Repeatable. |
| `--offline` | Never fetch; use local files and the cache only. |
| `--verbose` | Show passing checks too, not just problems. |
| `--json` | Emit the report as JSON. |
| `--output FILE` | Write the JSON report to a file. |

## Meta-schema versions

The meta-schemas belong to oold-schema. This package keeps a hand-curated copy of each released
version under `src/oold/validation/meta/<version>/`, so validation works offline and so one schema
can be checked against several versions at once.

```bash
oold validate ./schemas --meta 0.7.0 --meta 0.8.0
```

Only two checks depend on the version, `schema.meta` and `lint.pattern`, and only those are
repeated per version; everything else runs once. Results carry the version they came from, so a
difference between releases is visible rather than confusing. This is reproducible against the
committed fixtures:

```console
$ oold compliance tests/data/oold/compliance --offline --meta 0.7.0 --meta 0.8.0
FAIL  tests/data/oold/compliance
      meta-schema: 0.7.0, 0.8.0
      138 ok, 2 failed, 0 warning(s), 0 skipped, across 52 target(s)

  FAIL compliance.lint  ... @type: xsd:integer is never selected on the way back ... [0.7.0]
  FAIL compliance.lint  ... @type: xsd:boolean and xsd:double are rejected ... [0.7.0]
```

Both failures are real and expected: 0.8.0 extended the no-coercion rule from `xsd:string` to every
natively-JSON-encoded datatype, so fixtures written for 0.8.0 assert something 0.7.0's lint cannot
catch. The `[0.7.0]` tag is what tells you this is a version difference rather than a broken schema.

`remote` fetches the unreleased `main` state into `~/.cache/oold/meta/` (override with
`OOLD_CACHE_DIR`). It never writes into the tracked history, so a released version cannot change
meaning behind your back. Adding a version is documented in
`src/oold/validation/meta/README.md`.

## Rule citations

Every finding can cite the normative statement it enforces. Rule ids come from the specification's
catalog (`meta/oold-rules.json`, generated upstream from the spec prose) and are permanent, so they
can be quoted in a review or a changelog:

```console
$ oold validate Author.schema.json --verbose
  FAIL OOLD-RT-002 lint.container    Author.schema.json: strict array property without @container
       https://oo-ld.org/latest/spec/#rule-OOLD-RT-002
```

```bash
oold rules list                    # every rule, and the check that enforces it
oold rules list --area RT          # just round-trip safety
oold rules list --unchecked        # checkable rules no check enforces yet
oold rules explain OOLD-RT-002     # level, binding, spec text and link
```

The catalog was introduced upstream after 0.8.0, so no tracked version ships one yet; use
`--meta remote` until a release includes it. A version without a catalog is fully supported: it
validates exactly as before, findings simply carry no citation, and `coverage.rules` reports
`skip`.

Each rule records **who it binds**, which decides what can enforce it:

| `applies_to` | Meaning |
|---|---|
| `document` | Checkable by validating a schema or instance. These are what the validator can enforce |
| `implementation` | Constrains a library rather than a document; needs a conformance suite |
| `advisory` | Guidance that nothing verifies automatically |

`coverage.rules` reports the gap between the checkable rules and the checks that exist. It is a
**warning**, never a failure: the gap is what the catalog exists to make visible, and an id absent
from an older catalog is indistinguishable from a typo, so failing would break validation against
older meta versions for no reason. A genuine typo is caught instead by the opt-in parity test,
which resolves every mapping against the current upstream catalog.

## The checks

| Check | What it asserts |
|---|---|
| `schema.meta` | The schema validates against the OO-LD meta-schema. |
| `schema.refs` | Its `$ref` composition resolves. |
| `lint.pattern` | No term coerces a literal to a datatype JSON encodes natively (`xsd:string`, `xsd:boolean`, `xsd:integer`, `xsd:double`, `xsd:float`). None of those survive a round-trip. |
| `lint.container` | A strictly `type: array` property declares `@container: @set` or `@list`, or a single-element array returns as a scalar. |
| `lint.iri-format` | *(warning)* A bare-IRI-string reference declares an `iri-reference` or stricter `uri*` format. |
| `generate.satisfiable` | A generated instance validates against its own schema, catching unsatisfiable schemas. |
| `roundtrip.generated` | That instance survives instance → RDF → instance with no property lost, and the reconstruction still validates. |
| `context.remote` | The schema works as a remote `@context`. |
| `context.predicates` | Every declared property produces a grounded predicate. |
| `variants` | Each `oneOf`/`anyOf` branch is generated and round-tripped in turn. |
| `instance.schema` | A committed instance validates against its schema, with `format` asserted. |
| `roundtrip.instance` | It round-trips through RDF unchanged. |
| `compliance.*`, `coverage.vocab` | Fixture suites with exact expected outcomes, plus a cross-check that every meta-schema keyword has a test. |
| `coverage.rules` | *(warning)* Which checkable rules no check enforces yet. |

### Cyclic scoped contexts

When a schema's `@context` references form a cycle - a type whose scoped context embeds itself -
a JSON-LD processor must eagerly validate the recursive context. Neither PyLD nor jsonld.js bounds
that recursion, so such a schema cannot be round-tripped by either. Affected schemas have their
`roundtrip.*` and `context.remote` checks **skipped** with a note; every other check still runs.
Model cyclic edges as references (`@type: "@id"` plus `x-oold-range`, no scoped context).

## Library

```python
from oold.validation import Options, validate_directory, validate_schema

report = validate_schema("Person.schema.json", Options(meta=("latest",), offline=True))
if not report.passed:
    for check in report.failures():
        print(check.id, check.target, check.message)

print(report.to_dict("summary"))
```

`validate_instance` and `run_compliance` follow the same shape. Every entry point returns a
`Report` rather than raising: a caller asking about a broken schema wants the explanation.

## MCP server

A working config is committed at `.mcp.json`:

```json
{
  "mcpServers": {
    "oold-validation": {
      "command": "uv",
      "args": ["run", "--directory", ".", "python", "-m", "oold.validation.mcp_server"]
    }
  }
}
```

Transport is stdio. Tools: `validate_oold_schema`, `validate_oold_instance`,
`validate_oold_directory`, `run_oold_compliance`, `generate_oold_instance`,
`check_context_mapping`, `list_meta_versions`, `list_oold_rules`. Each takes `verbosity` as `"summary"` (default) or
`"full"`, and returns errors as data rather than raising.

## Differences from the reference harness

The two are intended to agree on verdicts. Where they differ, it is deliberate:

| Difference | Why |
|---|---|
| Remote and cross-directory `@context` references resolve | The reference maps only names directly under its own base and refuses everything else, so a schema whose context chain leaves the directory cannot be processed at all. `--offline` reproduces its behaviour. |
| Fetched documents are cached on disk | The reference refetches on every run. |
| `context.predicates` exists | Catches undefined-prefix terms, which round-trip cleanly while meaning nothing. |
| Results are reported per meta-schema version | Multi-version validation is not available upstream. |
| Generation is deterministic | The reference's faker already populates every property (`alwaysFakeOptionals`); making it deterministic removes flaky CI failures. There is no `--seed`. |
| An author-pinned `id` (`const`/`enum`/`default`) is not rewritten | The reference rewrites every generated `id` unconditionally, which would make such an instance violate its own schema. |
| `pattern`-constrained strings get a placeholder | Neither corpus uses `pattern`; this avoids a regex-generation dependency. Reported as a note. |

Check *counts* differ too, because this port splits some of the reference's combined sections.
Verdicts must not: `tests/test_validation/test_parity_live.py` asserts that against a real
checkout.

## Testing against the upstream repository

```bash
OOLD_SCHEMA_DIR=../oold-schema uv run pytest tests/test_validation -q
```

Without that variable the parity tests skip and the suite stays self-contained. With it, the full
validator runs over oold-schema's own `examples/` and `examples/compliance/`, and the overall
verdict is compared against `node scripts/validate.mjs`.

The `format` assertions are pinned separately: `tests/data/format_parity.json` holds 98 outcomes
captured from ajv as the reference configures it (`ajv-formats` in *full* mode, plus the
`iri`/`iri-reference` override `validate.mjs` applies), and the suite asserts Python agrees on
every one. Two are easy to get wrong: in full mode `time` requires an offset and `email` requires
a dotted domain.
