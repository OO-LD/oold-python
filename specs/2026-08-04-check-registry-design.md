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
    rule: str | None = None       # the OO-LD rule it enforces, when there is one
    default_status: Status = FAIL # status when it reports a problem and no rule applies
    per_version: bool = False     # emits once per selected meta-schema version
    detects: Callable | None = None  # the function implementing detection
    run: Predicate | None = None  # executable predicate, for self-contained checks
    predates_catalog: bool = False  # the requirement is older than the catalogue
```

Four fields deserve comment.

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

`run` is what lets this be **one** structure rather than two. The ten `rule.*` checks are
self-contained predicates over an already-resolved context, so the registry can execute them
directly. The other fourteen are driven by the pipeline phases and leave `run` empty. Where `run`
is set it is also the detection site, so `detects` defaults to it and is never written twice.

### One structure, not four

Today the same information is spread across four places:

| Today | Holds | Fate |
| --- | --- | --- |
| `RuleCheck` (`rule_checks.py`) | id, rule, description, predicate for 10 checks | Absorbed into `CheckInfo` |
| `RULE_CHECKS` | the 10 entries | Becomes `[c for c in CHECKS if c.run]` |
| `RULE_CHECK_MAP` | `{check_id: rule}` for those 10 | Deleted; it is `c.rule` |
| `CHECK_RULES` (`pipeline.py`) | 4 hand-written pairs plus the above | Deleted; it is `c.rule` |

All four collapse into a single `CHECKS: tuple[CheckInfo, ...]` in `check_registry.py`. There are
no derived mappings to keep in step, because there is nothing to derive from: the rule id is a
field on the check, looked up directly.

This answers the maintenance objection that motivated the design. Adding a rule check is still one
edit in one place, as it is today, and it now also registers the check for `oold checks` instead
of requiring a second entry somewhere else.

### Where the code lives

`check_registry.py` holds `CheckInfo`, `ContextView`, the ten predicates, `CHECKS`, `severity()`
and the driver that executes the runnable entries. `rule_checks.py` is **deleted**; its contents
move here, which is what makes this a single file rather than a registry plus a satellite.

The fourteen phase checks keep their detection where it already is, in `pattern_lint.py`,
`roundtrip.py`, `context_graph.py` and friends, because those are substantial algorithms rather
than five-line predicates. The registry references them for `detects`.

The import direction is one-way and verified acyclic: `check_registry` imports the detection
modules, none of which import it or each other in a cycle, and `pipeline` imports
`check_registry`. Expected size is roughly 430 lines, most of it the predicates that already
exist. If that ever feels too large, the predicates can move back out without changing the
structure, since the registry holds references either way.

### Versions: what runs against which specification

A new specification version states a new rule, the rule needs a check, and that check must not
fire when validating against an older version that never required it. The information that decides
this lives in the **vendored catalogue**, not in the code, and not in a version number written
into a check.

Gating is by presence: if the selected version's `oold-rules.json` does not list the rule, the
check is skipped with a message saying so. This is already how the ten `rule.*` checks behave, and
it means adding a check for a new rule needs **no backward-compatibility code at all**. Older
versions skip it because their catalogue does not mention it.

One field extends that to every check that names a rule:

```python
predates_catalog: bool = False
```

| Value | No catalogue (0.7.0, 0.8.0) | Catalogue present | Used by |
| --- | --- | --- | --- |
| `False` (default) | Skip | Run only if stated and not deprecated | Every new check |
| `True` | Run | Run only if stated and not deprecated | The four checks older than the catalogue |

The question the flag answers is "did this requirement exist before the catalogue did?", which is
the only thing a pre-catalogue version cannot tell us. Both values gate identically **wherever a
catalogue exists**; they differ only in what to assume where none does.

That matters more than it first appears. A naive "always run" flag for the legacy checks would be
wrong the moment one of their rules is superseded: the old check would keep firing against a new
version that no longer states its requirement. Gating on the catalogue whenever one is present
avoids that, while `True` preserves coverage on the two shipped versions that have none.

Today's four legacy checks are `lint.pattern`, `lint.container`, `lint.iri-format` and
`context.predicates`. All four rules are present and undeprecated in 1.0.0-rc.1, so `True`
reproduces current behaviour exactly on every tracked version.

That asymmetry is not arbitrary. It exists because **`since` cannot answer this question.** All 34
rules in the 1.0.0-rc.1 catalogue carry `since: 1.0.0-rc.1`, since that is when the catalogue was
minted rather than when the requirements appeared. So there is no machine-readable record of what
0.7.0 or 0.8.0 required, and the only safe reading for a pre-catalogue version is that
long-standing checks apply and newly-catalogued ones cannot be attributed. Any design that gated
on `since` would be wrong for exactly the two versions currently shipped.

### What a changed rule actually costs

Not every specification change reaches this repository, and the three cases differ a lot.

**Reworded, same requirement.** The rule id is unchanged by upstream policy, so nothing here
changes: same check, same registry entry, no new id. The work is one `make rules-accept` in
oold-schema, and the vendored catalogue's `text_sha256` moves when the version is next vendored.

**Changed requirement, detection driven by vendored data.** Often free. The precedent is 0.8.0,
where the no-coercion rule widened from `xsd:string` to every natively-encoded datatype. That
shipped entirely as a new `oold-pattern-lint.schema.json`, and `lint.pattern` picked it up by
vendoring the version. No Python changed, because the check executes the meta-schema rather than
reimplementing it. Anything expressible in the pattern-lint schema lands here.

**Changed requirement, bespoke detection.** This is the case in the question, and yes: upstream
mints a new rule id, and this repository gains a new predicate and a new registry entry. Both are
necessary rather than ceremonial, because both behaviours have to be available **at the same
time**: validating against the old version must apply the old requirement and the new version the
new one. Editing the check in place would silently change what older versions are judged by, which
is the failure this whole design exists to prevent.

The marginal cost over simply writing the new logic is **one registry line**. The old entry needs
no edit at all: its rule is now deprecated in the new catalogue, so it self-gates, keeps working
for older versions, and is reported as skipped with the id that superseded it. Nothing needs to
know which version is "current".

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
  per version no
```

The emitting site is deliberately not shown. It is findable by searching for the check id, which
already works, and printing it would mean either a second maintained field or a stack walk at
report time.

`--unmapped` lists the checks that enforce no rule, which is the mirror image of
`oold rules list --unchecked` and makes the boundary between the two identifier systems visible.

## Why this will not drift

The registry is hand-*written*, which is unavoidable: a one-line description of what a check does
exists nowhere else, so writing it down creates no second copy. It is not hand-*synced*, which is
what rots. Four tests hold it to reality, all using the existing fixture corpus:

1. **Every id emitted during the suite is in the registry.** Adding a check without registering it
   fails, naming the id.
2. **Every registry entry is emitted at least once by the suite.** This catches a stale entry for
   a check that was removed, and, usefully, a check that silently stopped running.
3. **Every non-null `rule` exists in at least one vendored catalogue.** Catches a typo'd or
   retired rule id.
4. **Under `--meta 0.7.0`, exactly the `predates_catalog` checks run.** Pins the backward
   compatibility promise to a test rather than to reviewer memory. 0.7.0 ships no catalogue, so a
   check written for a catalogued rule must skip there, and a legacy one must not. Both directions
   fail loudly, which is what stops a new check from quietly judging an old specification.

Test 2 is the one that makes this different from the rejected inventory. That file would only ever
have been compared against itself; this is compared against what the validator actually does.

## Explicitly out of scope

* **No change to verdicts.** Parity with the reference harness must hold unchanged. This adds
  metadata and a read-only command.
* **No change to the JSON report shape.** Consumers are unaffected.
* **No restructuring of the pipeline phases.** `pipeline.py` loses the `CHECK_RULES` table and
  reads the registry instead, but its control flow, phase functions and short-circuits are
  untouched. See below for why the tempting larger version is not attempted.
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

The ten `rule.*` checks work as a flat registry precisely because they are independent predicates
over an already-resolved `ContextView`; the phase checks are the work that produces it.
Adopting that shape everywhere therefore means designing an explicit dependency graph and a
fan-out mechanism, which is a redesign of execution semantics on code pinned by parity.

This design does not foreclose it. The registry is where such a migration would happen: entries
gain a `run=` callable one at a time, and phase functions shrink as checks move out. The ten
`rule.*` checks are already in that end state, which is evidence the target shape works here.

## Files

| File | Change |
| --- | --- |
| `src/oold/validation/check_registry.py` | New. `CheckInfo`, `ContextView`, the ten predicates, all 24 `CHECKS` entries, `severity()`, the driver, lookup helpers |
| `src/oold/validation/rule_checks.py` | **Deleted.** Contents move into `check_registry.py` |
| `src/oold/validation/pipeline.py` | `CHECK_RULES` deleted; reads `CheckInfo.rule` directly |
| `src/oold/validation/cli.py` | `oold checks list` / `oold checks explain` |
| `tests/test_validation/test_rule_checks.py` | Imports move to `check_registry`; otherwise unchanged, so the ten predicates keep their existing coverage |
| `tests/test_validation/test_check_registry.py` | New. The four drift tests |
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

Because `rule_checks.py` disappears, `git grep -n 'rule_checks\|RULE_CHECKS\|RULE_CHECK_MAP\|CHECK_RULES'`
must come back empty when the change is done. Any survivor is a mapping that was meant to die.

## Risks

**Descriptions decay quietly.** The tests check that ids and rules line up; no test can tell
whether a `summary` still describes what the code does. Mitigated only by keeping summaries short
and reviewing them when the check changes.

**`detects` is a judgement call for multi-site checks.** Pointing `roundtrip.generated` at one of
its five emission sites would mislead. The design allows `None` for exactly this, and the CLI must
say "no single detection site" rather than guess.

**Scope creep toward per-check functions.** The registry makes that refactor look easy. It is not,
for the reasons above, and it should be a separate decision with its own spec.
