# Maintaining the vendored meta-schemas and fixtures

The OO-LD meta-schemas are owned by [oold-schema](https://github.com/OO-LD/oold-schema). This
package vendors two things from it, and they must always come from the **same release tag**:

- `src/oold/validation/meta/<version>/` - a hand-curated copy of each released meta-schema
  version, so `oold` can validate offline and so one schema can be checked against several
  meta-schema versions in a single run.
- `tests/data/oold/` - a snapshot of oold-schema's `examples/` at the newest tracked version.

Both are read-only copies. Nothing here is written at runtime: `--meta remote` fetches the
unreleased `main` state into the user cache (`~/.cache/oold/meta/`, or `OOLD_CACHE_DIR`) and
never touches either vendored tree, so a released version cannot change meaning behind your back.

## Layout

```
src/oold/validation/meta/
├── index.json      provenance: upstream tag, commit, checksums, and the fixture slice's tag
├── 0.7.0/          oold-meta-schema.json, oold-pattern-lint.schema.json, oold-ui-meta-schema.json
├── 0.8.0/          the same three files
├── 1.0.0-rc.1/     those three, plus oold-rules.json and the oold-rules.schema.json describing it
├── 1.0.0-rc.2/     those five, plus oold-meta-schema-base.json, the body the dialect now $refs
└── <next>/
```

```
tests/data/oold/
├── .                   examples/ from the recorded tag, plus compliance/
├── broken/             deliberately broken schemas: the checks must fail on these
├── remote_context/     a schema whose @context chain leaves its directory
└── x_oold_context/     a schema mapping a term only through x-oold-context
```

Which version `latest` resolves to is deliberately not written down anywhere. It is the highest
one present, decided by `tracked_versions()`, and `oold meta list` prints it. A hand-maintained
copy of a derived fact only rots: this used to be stated in prose and was still naming an old
version two versions later.

## Byte-exactness

`src/oold/validation/meta/<version>/` and the vendored files under `tests/data/oold/` hold
verbatim copies of files from oold-schema release tags. `index.json` records a sha256 of each
meta-schema file, so they are not ordinary source files:

- never reformat them, and never let a formatting hook touch them (`.pre-commit-config.yaml`
  excludes these paths, `.gitattributes` marks them `-text`);
- they must be LF. A CRLF copy hashes differently, which passes on Windows and fails on Linux.
  This has happened; `test_the_vendored_files_are_stored_with_unix_line_endings` now guards it.

That is why every extraction command below uses `git cat-file blob`, never `git show`: `show`
applies the checkout's end-of-line conversion, so on Windows it writes CRLF, which changes every
digest and fails only once it reaches Linux CI.

## The file list is per source, not global

`index.json`'s top-level `files` is the *shared default* file set - the three meta-schemas the
older tracked versions ship. `meta_files(source)` reads it for a tracked version, or for `remote`,
but a source can override it with its own `files` entry when its set actually differs. Two sources
do. `1.0.0-rc.2` split the dialect meta-schema into a wrapper (`oold-meta-schema.json`,
document-level obligations) and a body it `$ref`s (`oold-meta-schema-base.json`, the keyword
syntax), so both that version and `remote` name four files instead of the shared three. The older
versions predate the split and are not made to load a file they do not have. Each list is declared
once, in `index.json`, rather than in code.

Any further file-set change is declared the same way: add a `files` list to that version's own
entry under `versions`, naming exactly what it ships. Omit it, and the version falls back to the
shared default. A file a source's list names but does not have is still a load error, not a silent
skip - drift here is exactly what this is meant to catch.

## Adding a version

When oold-schema cuts a release, from a checkout of it:

### 1. Vendor the meta-schema files

```bash
V=1.0.0
mkdir -p src/oold/validation/meta/$V
for f in oold-meta-schema oold-meta-schema-base oold-pattern-lint.schema oold-ui-meta-schema oold-rules oold-rules.schema; do
  git -C ../oold-schema cat-file blob v$V:meta/$f.json > src/oold/validation/meta/$V/$f.json
done
sha256sum src/oold/validation/meta/$V/*.json
git -C ../oold-schema rev-parse v$V
git -C ../oold-schema log -1 --format=%cI v$V
```

**Check what the release actually ships before running the loop.** The set has grown twice.
`oold-rules.json`, the catalogue of normative statements, and `oold-rules.schema.json`, which
describes it, arrived in 1.0.0-rc.1; `oold-meta-schema-base.json` arrived in 1.0.0-rc.2, when the
dialect split into a wrapper and the body it `$ref`s. Drop from the loop whatever a given version
predates, and name the set in that version's own `files` entry when it differs from the shared
default. Listing only the three meta-schemas here once cost a vendoring the catalogue entirely,
which is silent: findings simply stop citing rules and every `rule.*` check skips as though the
version had stated nothing. Omitting the base is not silent, but it fails obscurely, as an
unresolvable `$ref` rather than a missing file.

Extract from the **tag**, not from the working tree. The two diverge: at the time 0.7.0 was added,
`main` had already changed all three files, including the canonical `$id` domain.

The catalogue is the one exception, and only while it is unreleased. `1.0.0-rc.1`'s copy comes from
an oold-schema branch because no tag carries one yet; when that happens, record the branch and
commit under `rules_source` so the provenance is still exact. Never do this for a meta-schema.

Then add an entry to `index.json` with the tag, commit, commit date, the `$id` base in use for that
release (see "Why `id_base` is recorded and not assumed" below), and the checksums.

### 2. Refresh the fixture slice

Refresh `tests/data/oold/` from the **same tag**, so fixtures and meta-schemas always come from
one release, then record that tag as `fixtures.tag` in `index.json`:

```bash
V=$(uv run python -c "from oold.validation.meta_store import latest_version; print(latest_version())")
DEST=tests/data/oold
for f in $(git -C ../oold-schema ls-tree --name-only v$V examples/ | grep '\.json$'); do
  git -C ../oold-schema cat-file blob "v$V:$f" > "$DEST/$(basename $f)"
done
for f in $(git -C ../oold-schema ls-tree --name-only v$V examples/compliance/); do
  git -C ../oold-schema cat-file blob "v$V:$f" > "$DEST/compliance/$(basename $f)"
done
make validate
```

Then confirm both refreshes still pass:

```bash
uv run oold validate tests/data/oold --offline --meta all
make validate && uv run pytest tests/test_validation -q
```

Keeping the two in step is not cosmetic. A compliance fixture asserts the lint rules of the release
that introduced them, so a newer fixture set combined with an older meta-schema fails in ways that
say nothing about the code. `fixtures.tag` is what makes the pairing checkable rather than a habit:
`test_the_fixture_slice_records_the_release_it_came_from` compares it against the newest tracked
version, because this step has been skipped before and prose describing the tag in a README did
not notice - the sentence kept naming an old release after a vendoring had already moved the
fixture files on. The tag is recorded only in `index.json` now, for exactly that reason.

## The fixture slice

Only the top level and `compliance/` are the upstream snapshot; both come from `examples/` at the
recorded tag. `broken/`, `remote_context/` and `x_oold_context/` are written here by hand, exist
in no oold-schema release, and the refresh loop above never touches them. Upstream's `examples/`
also has a `spec/` subdirectory, which is deliberately outside the slice - the loops above do not
descend into it.

Upstream's current `main` is covered instead by the opt-in parity tests
(`tests/test_validation/test_parity_live.py`), which validate against `--meta remote`.

### `remote_context/Leaf.schema.json` requires `name`

That is deliberate: `name` is defined only in the remote `../Thing.schema.json`, while Leaf's own
inline `@context` defines just `nickname`. Any check that reads `schema["@context"]` instead of
the resolved context reports a violation here, on a schema that is entirely correct. Keep the
`required` when editing this fixture; without it the schema still exercises context resolution,
but nothing notices a check judging the literal context rather than the resolved one.

### Broken fixtures

Each one exists to prove a specific check fires, rather than only that valid input passes. One is a
control instead: the same schema without the defect, proving the check stays silent where the
specification says it must.
`tests/test_validation/test_pipeline.py` maps each file to the check it must trip.

| Fixture | Trips |
|---|---|
| `invalid_meta` | `schema.meta` - `x-oold-uuid` is not a UUID, so `format` has to be asserted |
| `missing_context_term` | `roundtrip.generated`, `context.predicates` - a property with no `@context` term |
| `undefined_prefix` | `context.predicates` - expands to a syntactically absolute IRI that means nothing |
| `unresolvable_context_ref` | `context.predicates` - the `@context` chain points at a missing schema |
| `xsd_string_coercion` | `lint.pattern` - a term coercing a literal to `xsd:string` never round-trips |
| `array_without_container` | `lint.container` - a strict array without `@container: @set` |
| `inline_type_disagrees` | `rule.instance-type` - a pinned `type` naming a class absent from `x-oold-instance-rdf-type` |
| `closed_object_rejects_metadata` | `rule.closed-object` - `additionalProperties: false` without declaring `$schema` and `@context` |
| `iri_reference_without_format` | `lint.iri-format` (warns, does not fail) - a bare-IRI-string reference with no `iri-reference`/`uri*` format |
| `base_uri_misaligned` | `rule.base-alignment` (warns, does not fail) - an `@base` that resolves a relative reference somewhere other than `$id` does |
| `legacy_dialect` | `rule.dialect-version` - `$schema` names `draft-07`, not a 2020-12-based dialect |
| `context_array_order_mismatch` | `rule.context-array-order` - `@context` lists two `allOf`-composed remote contexts out of order |
| `versioned_id_missing_version` | `rule.versioned-id` (warns, does not fail) - `x-oold-version` does not appear in an absolute `$id` |
| `root_ref_not_reflected` | `rule.context-reflects-refs` - a single `allOf` `$ref` is not reflected anywhere in `@context` |
| `branch_context_conflict` | `rule.branch-context-conflict` - two `oneOf`-branch contexts map the same keyword to different IRIs at the root |
| `narrow_only_relaxation` | `rule.narrow-only` - an `allOf` ancestor's `maximum` is relaxed rather than tightened (`NarrowBase.schema.json` is its sibling ancestor) |
| `vocab_covers_the_remainder` | nothing, deliberately - `missing_context_term` with `@vocab` added and nothing else changed, the control for `context.coverage` |

## Why `id_base` is recorded and not assumed

The `$id` domain has already moved once, from
`https://oo-ld.github.io/oold-schema/latest/meta/` (0.7.0) to `https://oo-ld.org/latest/meta/`
(post-0.7.0). Released copies also stamp the version in place of `latest`. The registry therefore
resolves cross-document `$ref`s by file name rather than by any fixed URL, and `id_base` is
documentation rather than something the code depends on.
