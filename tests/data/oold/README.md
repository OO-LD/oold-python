# OO-LD test fixtures

A snapshot of [oold-schema](https://github.com/OO-LD/oold-schema) `examples/`, taken at tag
**v0.8.0** - the same release the newest tracked meta-schemas in
`src/oold/validation/meta/0.8.0/` come from.

That pairing matters. A compliance fixture asserts the lint rules of the version that introduced
them, so combining a newer fixture set with an older meta-schema produces failures that say
nothing about this code. Upstream's current `main` is covered instead by the opt-in parity tests
(`tests/test_validation/test_parity_live.py`), which validate against `--meta remote`.

```
.                     examples/ from v0.8.0, plus compliance/
broken/               deliberately broken schemas: the checks must fail on these
remote_context/       a schema whose @context chain leaves its directory
```

## Refreshing the snapshot

When a new oold-schema version is tracked in `src/oold/validation/meta/`, refresh this slice from
the *same tag* so the two stay in step:

```bash
V=0.8.0
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
