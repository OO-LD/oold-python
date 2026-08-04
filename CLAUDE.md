# Working in this repository

Guidance for AI agents. Human contributors want `CONTRIBUTING.md`, which this file does not repeat.

## Commands

```bash
make check      # lint, type-check, dependency audit
make test       # pytest with coverage
make validate   # run the validator over the committed fixtures
make docs-test  # strict docs build, fails on any warning

OOLD_SCHEMA_DIR=../oold-schema uv run pytest -m parity   # compare against the reference harness
```

The parity tests skip silently without `OOLD_SCHEMA_DIR`, so a green `make test` does not mean
parity holds. Run them explicitly when touching `src/oold/validation/`.

## The validation subsystem

`src/oold/validation/` is a native Python port of `oold-schema/scripts/validate.mjs`, deliberately
not a subprocess wrapper. The reference harness is still the oracle: the parity tests assert this
port reaches the same verdicts on the same fixtures, including check labels and triple counts.

**Changes here must not change verdicts unless that is the point of the change.** Reporting,
wording and detail payloads are free to move; a schema that passed must still pass. If parity
drops, treat it as a defect in this port until proven otherwise. Upstream has been wrong before,
but that is the rarer case.

### Rules come from the specification, not from this code

The OO-LD spec numbers its normative statements (`OOLD-RT-002`) and publishes them as
`oold-rules.json`, vendored per version under `src/oold/validation/meta/<version>/`. Three
consequences that are easy to get wrong:

- **Severity is read, never written.** A check reports a problem; whether that is a failure or a
  warning comes from the rule's `level` in the catalogue. Do not reintroduce a hardcoded
  FAIL/WARN column. This is what lets one code base validate against several spec versions.
- **Skip rather than guess.** A rule absent from the selected version's catalogue, or marked
  deprecated there, is skipped with a message saying so. Older versions ship no catalogue at all
  and skip the whole `rule.*` family. Never fall back to "check it anyway".
- **Judge the resolved context.** Checks receive a `ContextView`, which is what terms mean after
  remote contexts and prefixes are applied. Reading `schema["@context"]` directly reports
  violations against correct schemas.

A false positive costs far more than a missed finding, because it teaches people to ignore the
output. When a rule is only partly decidable, check the part you are sure of.

### Vendored meta-schemas are byte-exact

`src/oold/validation/meta/<version>/` holds verbatim copies from oold-schema release tags, and
`index.json` records a sha256 of each. They are therefore not ordinary source files:

- never reformat them, and never let a formatting hook touch them (`.pre-commit-config.yaml`
  excludes these paths, `.gitattributes` marks them `-text`);
- they must be LF. A CRLF copy hashes differently, which passes on Windows and fails on Linux.
  This has happened; `test_the_vendored_files_are_stored_with_unix_line_endings` now guards it;
- to add a version, follow `src/oold/validation/meta/README.md` and recompute the digests.

## This repo and oold-schema are decoupled on purpose

They release on separate schedules, so neither pipeline waits on the other:

- `coverage.rules` **warns** when a rule has no check, rather than failing. A spec that has moved
  ahead must not break this build.
- Adding a check for a rule is described in `CONTRIBUTING.md#translating-a-specification-rule`.
  oold-schema's `make check` prints that link when the catalogue changes.

Do not add a check for a rule that is not in any vendored catalogue. Vendor the version first.

## Check ids are a public interface

Check ids (`lint.container`, `roundtrip.instance`, `rule.id-fragment`) appear in reports, CI logs
and, before long, in suppression comments. Renaming one silently breaks whatever depended on it,
and unlike rule ids there is no guard. Treat a rename as a breaking change: say so in the commit,
and prefer adding a new id over repurposing an existing one.

## Conventions

- Conventional Commits; releases are automated by python-semantic-release, so the type prefix
  decides the version bump.
- No AI attribution or co-author trailers in commits or PR descriptions.
- In prose and comments, use regular dashes rather than em or en dashes.
- Do not create scratch files inside this repository or in `../oold-schema`. To see what a file
  looks like on a clean checkout, read git state (`git show :path`, `git check-attr`) instead of
  deleting and restoring it.
