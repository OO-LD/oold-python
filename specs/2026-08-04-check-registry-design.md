# A registry for check ids, and `oold checks`

Status: proposed. Supersedes the "frozen inventory" idea discussed on 2026-08-04 and not built.

## The problem

A finding names the check that produced it:

```
FAIL OOLD-RT-002 lint.container   array_without_container.schema.json: strict array property
                                  without @container @set/@list: tags
```

Two questions have no good answer today.

**Where is the code that decided this?** A check is implemented in two places. The detection lives
in a concern module, the id and the message live in `pipeline.py`:

| Part of `lint.container` | Location |
| --- | --- |
| Detection | `pattern_lint.array_properties_missing_container` |
| Id, severity, message | `pipeline.py:224` |

Grepping `lint.container` finds only the second. The function that actually decides whether the
schema is wrong has a different name, in a different module, and nothing links the two.

**What checks exist at all?** The set of check ids is an emergent property of the code. Nothing
states it, so it cannot be listed, documented, or verified. Ten of the twenty-four ids enforce no
specification rule, so for those the check id is the only identifier a user has.

## What was settled first

This design follows a decision about identifiers that is worth recording, because it constrains
everything below.

The validator emits two kinds of identifier, and they are **not** peers:

* **Rule ids** (`OOLD-RT-002`) answer *which requirement was violated*. They are owned by the
  specification, permanent, and already guarded in oold-schema by `rules_baseline.py`. This is
  what belongs in a review comment or a changelog.
* **Check ids** (`lint.container`) answer *which check found it*. They are owned by this
  repository and follow the implementation.

Both are needed, for two reasons that are easy to miss:

1. **Ten of the twenty-four checks have no rule and never will.** `schema.meta` is definitional:
   validating against the meta-schema is what *being* an OO-LD schema means, not a numbered
   requirement inside it. `generate.satisfiable`, `variants` and `roundtrip.*` are this
   validator's methodology, which the specification does not mandate. `coverage.*` are self-tests
   about the fixture suite. Minting rule ids for these would push one tool's implementation
   strategy into the specification.
2. **Rule ids are not always available.** Validating the same schema against 0.7.0, which ships no
   catalogue, produces `FAIL lint.container` with no rule id at all. The check id is the
   identifier that survives every specification version.

Consequently check ids are **implementation-defined**: durable citations should use the rule id.
Two things follow, and neither is built here: no append-only policy for check ids, and no
stability guard. An earlier proposal for a committed list of ids compared by a test was rejected,
correctly, as a second hand-synced bookkeeping file duplicating information already in the code.

## Design

A registry of check metadata, and a CLI to read it.

### The record

```python
@dataclass(frozen=True)
class CheckInfo:
    id: str                       # "lint.container"
    summary: str                  # one line: what it verifies
    rule: str | None              # the OO-LD rule it enforces, when there is one
    default_status: Status        # FAIL or WARN when it reports a problem
    per_version: bool             # emits once per selected meta-schema version
    detects: Callable | None      # the function implementing detection
```

Three fields deserve comment.

`detects` holds **the function object, never a string path**. This is the difference between
metadata that rots and metadata that cannot. A hand-typed `"pattern_lint.array_properties_..."`
goes stale the moment anyone renames the function, silently. A reference either follows the rename
or fails to import. The displayed location is derived from it with `inspect`, so it is computed
rather than maintained. Where a check has no single detection site, `detects` is `None` and the
CLI says so rather than pointing somewhere misleading.

`per_version` records the fan-out that already exists: `schema.meta` and `lint.pattern` run once
per selected meta-schema version, so one id can produce several report lines.

`default_status` documents severity for checks that have no rule. For checks that do have one,
severity comes from the rule's `level` in the catalogue, and this field records only what happens
when no catalogue applies.

### Where entries come from

The registry has 24 entries and **10 of them are generated**, not authored:

* the `rule.*` family already exists as `RULE_CHECKS` in `rule_checks.py`, whose entries carry
  `check_id`, `rule`, `describe` and the predicate. `CheckInfo` records are derived from them
  directly, so adding a rule check keeps requiring exactly one edit, in one place;
* the remaining 14 phase checks are authored, one line each, next to the existing `CHECK_RULES`
  table in `pipeline.py` that this replaces.

`CHECK_RULES` and `RULE_CHECK_MAP` become views over the registry rather than separate tables, so
the check-to-rule mapping stops existing in two places.

### The command

Mirrors `oold rules`, which already exists, so there is one idiom to learn:

```
oold checks list [--prefix lint.] [--unmapped]
oold checks explain lint.container
```

```
lint.container   FAIL by default
  A strictly array-typed property must declare @container @set or @list.

  rule       OOLD-RT-002   (stated by 1.0.0-rc.1; absent from 0.7.0, 0.8.0)
  detected   pattern_lint.array_properties_missing_container   (pattern_lint.py:112)
  reported   pipeline.py, search for "lint.container"
  per version no
```

`--unmapped` lists the checks that enforce no rule, which is the mirror image of
`oold rules list --unchecked` and makes the boundary between the two identifier systems visible.

## Why this will not drift

The registry is hand-*written*, which is unavoidable: a one-line description of what a check does
exists nowhere else, so writing it down creates no second copy. It is not hand-*synced*, which is
what rots. Three tests hold it to reality, all using the existing fixture corpus:

1. **Every id emitted during the suite is in the registry.** Adding a check without registering it
   fails, naming the id.
2. **Every registry entry is emitted at least once by the suite.** This catches a stale entry for
   a check that was removed, and, usefully, a check that silently stopped running.
3. **Every non-null `rule` exists in at least one vendored catalogue.** Catches a typo'd or
   retired rule id.

Test 2 is the one that makes this different from the rejected inventory. That file would only ever
have been compared against itself; this is compared against what the validator actually does.

## Explicitly out of scope

* **No change to verdicts.** Parity with the reference harness must hold unchanged. This adds
  metadata and a read-only command.
* **No change to the JSON report shape.** Consumers are unaffected.
* **No restructuring of `pipeline.py`.** See below.
* **No stability guard or append-only policy for check ids**, per the decision recorded above.

## Relationship to per-check functions

The tempting larger version, one function per check id named to match (`lint.container` in
`lint.py` as `container()`, the ESLint layout), is **not** attempted, and the reason is specific
rather than general caution. Three properties of the current pipeline resist a flat registry of
predicates:

* **Checks short-circuit.** `pipeline.py:194` and `:198` return early when `$ref`s do not resolve,
  because linting a schema that could not be assembled produces noise. ESLint rules are mutually
  independent; these are stages in a dependency chain.
* **One id fans out.** `schema.meta` and `lint.pattern` emit per meta version, `variants` per
  composition variant.
* **One id emits several statuses from several sites.** `roundtrip.generated` reports SKIP for a
  cyclic context, FAIL for a processing error, FAIL for a shape mismatch, and OK, from five
  places. A predicate returning a list of problems cannot express a skip.

`rule_checks.py` works as a flat registry precisely because its ten checks are independent
predicates over an already-resolved `ContextView`; the phase checks are the work that produces it.
Adopting that shape everywhere therefore means designing an explicit dependency graph and a
fan-out mechanism, which is a redesign of execution semantics on code pinned by parity.

This design does not foreclose it. The registry is where such a migration would happen: entries
gain a `run=` callable one at a time, and phase functions shrink as checks move out. The ten
`rule.*` checks are already in that end state, which is evidence the target shape works here.

## Files

| File | Change |
| --- | --- |
| `src/oold/validation/registry.py` | New. `CheckInfo`, the 14 authored entries, derivation of the 10 from `RULE_CHECKS`, lookup helpers |
| `src/oold/validation/pipeline.py` | `CHECK_RULES` becomes a view over the registry |
| `src/oold/validation/cli.py` | `oold checks list` / `oold checks explain` |
| `tests/test_validation/test_registry.py` | New. The three drift tests |
| `docs/how-to/validation.md` | Document the two identifier systems and the new command |
| `CONTRIBUTING.md` | Registering a check, in the existing rule-translation section |
| `CLAUDE.md` | Correct the "check ids are a public interface" section, which overstates the case and predates this decision |

## Verification

```bash
uv run pytest tests/test_validation -q
uv run oold checks list
uv run oold checks explain lint.container
uv run oold checks list --unmapped              # expect the 10 rule-less checks

make validate                                   # verdicts unchanged
OOLD_SCHEMA_DIR=../oold-schema uv run pytest -m parity   # must stay 6/6
```

The parity run is the load-bearing one: this change must be invisible to verdicts.

Then confirm the drift tests actually fail, rather than trusting them: add a check id without
registering it, and delete a registry entry for a live check. Both must fail naming the id.

## Risks

**Descriptions decay quietly.** The tests check that ids and rules line up; no test can tell
whether a `summary` still describes what the code does. Mitigated only by keeping summaries short
and reviewing them when the check changes.

**`detects` is a judgement call for multi-site checks.** Pointing `roundtrip.generated` at one of
its five emission sites would mislead. The design allows `None` for exactly this, and the CLI must
say "no single detection site" rather than guess.

**Scope creep toward per-check functions.** The registry makes that refactor look easy. It is not,
for the reasons above, and it should be a separate decision with its own spec.
