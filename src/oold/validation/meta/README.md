# Meta-schema version history

The OO-LD meta-schemas are owned by [oold-schema](https://github.com/OO-LD/oold-schema). This
folder holds a hand-curated copy of each **released** version so `oold` can validate offline and so
one schema can be checked against several meta-schema versions in a single run.

```
meta/
├── index.json      provenance: upstream tag, commit, checksums, and the fixture slice's tag
├── 0.7.0/          oold-meta-schema.json, oold-pattern-lint.schema.json, oold-ui-meta-schema.json
├── 0.8.0/          the same three files
├── 1.0.0-rc.1/     those three, plus oold-rules.json and the oold-rules.schema.json describing it
├── 1.0.0-rc.2/     those five, plus oold-meta-schema-base.json, the body the dialect now $refs
└── <next>/
```

Which version `latest` resolves to is deliberately not written down here. It is the highest one
present, decided by `tracked_versions()`, and `oold meta list` prints it. A hand-maintained copy of
a derived fact only rots: this line used to name 0.8.0 and was still naming it two versions later.

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

Nothing here is written at runtime. `--meta remote` fetches the unreleased `main` state into the
user cache (`~/.cache/oold/meta/`, or `OOLD_CACHE_DIR`) and never touches this folder, so a released
version cannot change meaning behind your back.

## Adding a version

When oold-schema cuts a release, from a checkout of it:

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

`cat-file blob`, not `show`: `show` applies the checkout's end-of-line conversion, so on Windows it
writes CRLF, which changes every digest and fails only once it reaches Linux CI.

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
release, and the checksums.

Finally refresh the fixture slice in `tests/data/oold/` from the **same tag** (see its README) and
update `fixtures.tag` in `index.json` to match, so that fixtures and meta-schemas always come from
one release. Then confirm both still pass:

```bash
uv run oold validate tests/data/oold --offline --meta all
make validate && uv run pytest tests/test_validation -q
```

Keeping the two in step is not cosmetic. A compliance fixture asserts the lint rules of the release
that introduced them, so a newer fixture set combined with an older meta-schema fails in ways that
say nothing about the code. `fixtures.tag` is what makes the pairing checkable rather than a habit:
`test_the_fixture_slice_records_the_release_it_came_from` compares it against the newest tracked
version, because this step has been skipped before and prose did not notice.

## Why `id_base` is recorded and not assumed

The `$id` domain has already moved once, from
`https://oo-ld.github.io/oold-schema/latest/meta/` (0.7.0) to `https://oo-ld.org/latest/meta/`
(post-0.7.0). Released copies also stamp the version in place of `latest`. The registry therefore
resolves cross-document `$ref`s by file name rather than by any fixed URL, and `id_base` is
documentation rather than something the code depends on.
