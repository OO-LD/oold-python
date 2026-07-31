# Meta-schema version history

The OO-LD meta-schemas are owned by [oold-schema](https://github.com/OO-LD/oold-schema). This
folder holds a hand-curated copy of each **released** version so `oold` can validate offline and so
one schema can be checked against several meta-schema versions in a single run.

```
meta/
├── index.json      provenance: upstream tag, commit, checksums
├── 0.7.0/          oold-meta-schema.json, oold-pattern-lint.schema.json, oold-ui-meta-schema.json
├── 0.8.0/          same three files; `latest` resolves here
└── <next>/
```

Nothing here is written at runtime. `--meta remote` fetches the unreleased `main` state into the
user cache (`~/.cache/oold/meta/`, or `OOLD_CACHE_DIR`) and never touches this folder, so a released
version cannot change meaning behind your back.

## Adding a version

When oold-schema cuts a release, from a checkout of it:

```bash
V=0.8.0
mkdir -p src/oold/validation/meta/$V
for f in oold-meta-schema oold-pattern-lint.schema oold-ui-meta-schema; do
  git -C ../oold-schema show v$V:meta/$f.json > src/oold/validation/meta/$V/$f.json
done
sha256sum src/oold/validation/meta/$V/*.json
git -C ../oold-schema rev-parse v$V
git -C ../oold-schema log -1 --format=%cI v$V
```

Extract from the **tag**, not from the working tree. The two diverge: at the time 0.7.0 was added,
`main` had already changed all three files, including the canonical `$id` domain.

Then add an entry to `index.json` with the tag, commit, commit date, the `$id` base in use for that
release, and the checksums.

Finally refresh the fixture slice in `tests/data/oold/` from the **same tag** (see its README), so
that fixtures and meta-schemas always come from one release, and confirm both still pass:

```bash
uv run oold validate tests/data/oold --offline --meta all
make validate && uv run pytest tests/test_validation -q
```

Keeping the two in step is not cosmetic. A compliance fixture asserts the lint rules of the release
that introduced them, so a newer fixture set combined with an older meta-schema fails in ways that
say nothing about the code.

## Why `id_base` is recorded and not assumed

The `$id` domain has already moved once, from
`https://oo-ld.github.io/oold-schema/latest/meta/` (0.7.0) to `https://oo-ld.org/latest/meta/`
(post-0.7.0). Released copies also stamp the version in place of `latest`. The registry therefore
resolves cross-document `$ref`s by file name rather than by any fixed URL, and `id_base` is
documentation rather than something the code depends on.
