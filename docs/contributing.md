# Contributing

Contributions are welcome! You can help by reporting bugs, implementing features, or improving documentation. File issues and PRs at [github.com/OO-LD/oold-python](https://github.com/OO-LD/oold-python).

---

## Development Setup

Requires `uv` and `git`.

=== "SSH"

    ```bash
    git clone git@github.com:YOUR_NAME/oold-python.git
    cd oold-python
    ```

=== "HTTPS"

    ```bash
    git clone https://github.com/YOUR_NAME/oold-python.git
    cd oold-python
    ```

### Install the environment and hooks

=== "make"

    ```bash
    make install
    ```

=== "without make"

    ```bash
    uv sync --all-extras
    uv run pre-commit install
    ```

`pre-commit install` installs both the `pre-commit` and `commit-msg` stage hooks (via
`default_install_hook_types`); the latter enforces Conventional Commits (see below).

---

## Making Changes

1. Create a branch: `git checkout -b name-of-your-fix`
2. Make your changes and add tests in `tests/`
3. Run checks and tests (see below)
4. Commit and push, then open a pull request

### Checks and tests

=== "make"

    ```bash
    make check   # lint, type-check, dependency audit
    make test    # pytest with coverage
    ```

=== "without make"

    ```bash
    uv lock --locked
    uv run pre-commit run -a
    uv run ty check
    uv run deptry src
    uv run python -m pytest --cov --cov-config=pyproject.toml --cov-report=xml
    ```

### Docs

Doc sources live in `docs/`. The site is configured in `zensical.toml`.

=== "make"

    ```bash
    make docs        # serve with live reload at http://localhost:8000
    make docs-test   # strict build - fails on any warning
    ```

=== "without make"

    ```bash
    uv run zensical serve
    uv run zensical build -s
    ```

---

## Translating a specification rule

The OO-LD specification numbers each of its normative statements (`OOLD-RT-08f2`, ...) and
publishes them as `oold-rules.json`, which this repository vendors per meta-schema version (see
[Maintaining the vendored meta-schemas and fixtures](maintaining-meta-schemas.md)). When
oold-schema adds a rule, its `make check` prints a pointer back to this section, because a new
rule is the moment the validator falls behind the specification.

Not every rule becomes a check, so start by reading it:

```bash
uv run oold rules explain OOLD-RT-08f2
uv run oold rules list --unchecked        # everything still waiting for a check
```

`applies_to` decides whether there is anything to do here:

| `applies_to` | Meaning | Action |
| --- | --- | --- |
| `document` + `machine_checkable: true` | Decidable by looking at a schema or instance | Add a check, as below |
| `document`, not `machine_checkable` | Binds documents but needs human judgement | Nothing; it stays listed as unchecked |
| `implementation` | Constrains what the library *does*, which no validator can see | A test against the library, not a `CheckInfo` |
| `advisory` | Guidance only | Nothing |

To add a check, write the predicate and append a `CheckInfo` to `CHECKS` in
`src/oold/validation/check_registry.py`, alongside the existing entries:

```python
def _missing_id(schema: dict[str, Any], context: ContextView) -> list[str]:
    if not schema.get("$id"):
        return ["schema declares no $id, so it has no global identifier"]
    return []


CHECKS = (
    CheckInfo("rule.id", "a schema has a $id", rule="OOLD-VER-3b96", per_version=True, run=_missing_id),
    ...
)
```

The check id, a short description, the rule it enforces, and the predicate are what matter here.
Use a `rule.*` check id: `lint.*`, `schema.*` and `roundtrip.*` are checks that predate this
convention, and several of them already cite a rule.

The predicate returns a list of problem strings, empty when the schema conforms. Four things
about it are easy to get wrong:

- **Judge the resolved context, not the literal one.** `ContextView` is what the term definitions
  mean after remote contexts and prefixes are applied. Reading `schema["@context"]` directly will
  report violations for schemas that are perfectly correct.
- **Do not set a severity.** It comes from the rule's own `level` in the catalogue, so a `MUST`
  fails and a `SHOULD` warns without the check deciding anything. That is what lets one code base
  validate against several specification versions.
- **Prefer skipping to guessing.** A rule absent from the selected version's catalogue is skipped
  automatically. If a rule is only partially decidable, check the part you are sure of; a false
  positive costs far more than a missed finding, because it teaches people to ignore the output.
- **Leave `predates_catalog` alone.** It defaults to `False`, which is right for a new rule.
  Setting it `True` claims the requirement is older than the catalogue itself, and makes the check
  run against 0.7.0 and 0.8.0, which ship no catalogue and never stated your rule. It is reserved
  for the handful of checks that predate the catalogue. This one fails silently in the wrong
  direction: nothing breaks, the old versions are simply judged by a rule that postdates them.
  `test_predates_catalog_is_exactly_what_runs_under_a_pre_catalogue_version` is the guard.

### What the check owes in tests

Unit tests in `tests/test_validation/test_check_registry.py` are the obligation: one schema that
conforms and one that violates. A check that only ever sees valid input is not known to fire at
all. A `rule.*` predicate is a pure function of `(schema, ContextView)`, so a test constructs the
`ContextView` directly and there is nothing else to arrange.

A fixture under `tests/data/oold/broken/` is **not** expected of a `rule.*` check, and none of the
existing ones has one. Those fixtures exist for checks whose verdict depends on machinery a unit
test cannot stub - `schema.meta` compiling a meta-schema, `roundtrip.generated` making a real RDF
round trip, `context.predicates` running a real JSON-LD expansion. Add one only if your check is of
that kind.

There is a third obligation neither of those covers, and it is the one that has actually gone
missing: **at least one schema in `tests/data/oold/` must exercise the predicate through the
pipeline.** Isolated unit tests prove the predicate is correct, never that it is reached with a
correctly resolved `ContextView`. If the corpus gives your check nothing to judge, it passes
everywhere and proves nothing; extend a fixture until it does. `remote_context/Leaf.schema.json`
carries a `required` for exactly this reason.

Finally, confirm the gap actually closed:

```bash
uv run oold rules list --unchecked        # the rule should be gone from this list
make validate                             # coverage.rules reports one fewer unchecked rule
```

`coverage.rules` warns rather than fails, deliberately: the specification and this validator
release on separate schedules, and a spec that has moved ahead should not break this build.

---

## Commit messages (Conventional Commits)

This project uses [Conventional Commits](https://www.conventionalcommits.org/).
Commit messages drive versioning and the changelog automatically, so the format
matters. The local `commit-msg` hook rejects malformed messages.

Format: `type(scope): subject`, for example `fix: correct sidebar collapse on
small screens`. The scope is optional.

| Type | Release effect | Use for |
| ---- | -------------- | ------- |
| `feat` | minor bump | a new feature |
| `fix` | patch bump | a bug fix |
| `perf` | patch bump | a performance improvement |
| `docs`, `chore`, `test`, `refactor`, `ci`, `style`, `build` | no release | changes that do not ship user-facing behavior |
| `BREAKING CHANGE:` footer, or `!` after the type | major bump | an incompatible change |

A breaking change is marked either with a `!` (`feat!: drop Python 3.9`) or a
`BREAKING CHANGE:` footer in the commit body.

---

## Releasing

Releases are fully automated by python-semantic-release. You do not tag or bump
the version by hand.

1. Open a PR. CI comments the version that a merge would release, based on your
   commits.
2. Merge to `main`. On merge, CI reads the new conventional commits, bumps the
   version in `pyproject.toml` and `CITATION.cff`, updates `CHANGELOG.md`,
   commits with `[skip ci]`, and pushes the `vX.Y.Z` tag.
3. CI then builds the package, publishes it to PyPI via OIDC trusted publishing,
   and deploys the docs to GitHub Pages.

If a merge contains only non-releasing commit types (for example `docs` or
`chore`), no release is cut. The version lives in `pyproject.toml`; never edit it
manually.

---

## Citation and authorship

Authors of the project are listed explicitly in `CITATION.cff`. This list is the set of creators shown on each [Zenodo](https://zenodo.org/doi/10.5281/zenodo.8374237) release. We keep it opt-in and curated rather than auto-generated from GitHub, so nobody is listed without consent, and the entries in `CITATION.cff` take precedence over GitHub's automatic contributor detection.

To be officially listed as an author for future Zenodo releases, add yourself to the `authors:` list in `CITATION.cff`. Two ways, in order of preference:

1. **Preferred - within your feature PR:** include the `CITATION.cff` edit directly in the same PR that contributes your feature or fix, so authorship is recorded together with the work.
2. **Standalone PR:** if you are already a GitHub contributor and simply want to be listed as an author on Zenodo, open a single PR that only adds your entry.

In either case, add an entry like:

```yaml
  - given-names: Your
    family-names: Name
    affiliation: "Your institution"                 # optional
    orcid: "https://orcid.org/0000-0000-0000-0000"  # optional, use your real ORCID
```

Notes:

- Append yourself to the end of the list (order is the citation order); mention it in the PR if a different position is intended.
- `affiliation` and `orcid` are optional but recommended for durable, unambiguous attribution.
- Only entries present in `CITATION.cff` at the tagged commit appear on that release's Zenodo record, so add yourself before a release to be included.

---

## Conventions

A few rules apply equally to human contributors and to AI agents working in this repository:

- No AI attribution or co-author trailers in commits or PR descriptions.
- In prose and comments, use regular dashes rather than em or en dashes.
- Do not create scratch files inside this repository or in a sibling checkout of `oold-schema`.
  To see what a file looks like on a clean checkout, read git state (`git show :path`,
  `git check-attr`) instead of deleting and restoring it.

---

## AI Guidelines

We believe that AI, and in particular LLMs, can be helpful conventional tools to accelerate development and improve quality when used responsibly. AI or any other tool is never the author of code; a human developer always is. Therefore, it is mandatory to carefully review all generated content for correctness, quality, and the absence of legal and ethical issues. For consistency, please avoid patterns that are hard to maintain manually, such as duplicated content or special characters like em dashes or UTF icons.
