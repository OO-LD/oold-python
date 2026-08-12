# OO-LD test fixtures

A snapshot of [oold-schema](https://github.com/OO-LD/oold-schema) `examples/`, taken at the release
that `src/oold/validation/meta/index.json` records under `fixtures.tag` - always the newest version
tracked beside it.

That pairing matters. A compliance fixture asserts the lint rules of the version that introduced
them, so combining a newer fixture set with an older meta-schema produces failures that say
nothing about this code. Upstream's current `main` is covered instead by the opt-in parity tests
(`tests/test_validation/test_parity_live.py`), which validate against `--meta remote`.

The tag is recorded in `index.json` rather than written here on purpose. It used to be stated in
this paragraph, and a vendoring updated the fixture files without updating the sentence describing
them, so the README claimed v0.8.0 for a full release while the slice was v1.0.0-rc.1. Nothing
noticed, because prose is not checked.
`test_the_fixture_slice_records_the_release_it_came_from` now checks the recorded value.

```
.                     examples/ from the recorded tag, plus compliance/
broken/               deliberately broken schemas: the checks must fail on these
remote_context/       a schema whose @context chain leaves its directory
```

Only the top level and `compliance/` are the upstream snapshot. `broken/` and `remote_context/`
are written here, exist in no oold-schema release, and the refresh below never touches them.

`remote_context/Leaf.schema.json` requires `name`, and that is deliberate: `name` is defined
only in the remote `../Thing.schema.json`, while Leaf's own inline `@context` defines just
`nickname`. Any check that reads `schema["@context"]` instead of the resolved context reports a
violation here, on a schema that is entirely correct. Keep the `required` when editing this
fixture; without it the schema still exercises context resolution, but nothing notices a check
judging the literal context rather than the resolved one.

## Refreshing the snapshot

When a new oold-schema version is tracked in `src/oold/validation/meta/`, refresh this slice from
the *same tag* so the two stay in step, then record that tag as `fixtures.tag` in `index.json`:

```bash
V=$(uv run python -c "from oold.validation.meta_store import latest_version; print(latest_version())")
DEST=tests/data/oold
for f in $(git -C ../oold-schema ls-tree --name-only v$V examples/ | grep '\.json$'); do
  git -C ../oold-schema show "v$V:$f" > "$DEST/$(basename $f)"
done
for f in $(git -C ../oold-schema ls-tree --name-only v$V examples/compliance/); do
  git -C ../oold-schema show "v$V:$f" > "$DEST/compliance/$(basename $f)"
done
make validate
```

## Broken fixtures

Each one exists to prove a specific check fires, rather than only that valid input passes.
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
