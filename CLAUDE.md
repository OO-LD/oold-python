# Working in this repository

Guidance for AI agents. Human contributors want the published contributing guide
([docs/contributing.md](docs/contributing.md)), which this file does not repeat.

## Commands

```bash
make check      # lint, type-check, dependency audit
make test       # pytest with coverage
make validate   # run the validator over the committed fixtures
make docs-test  # strict docs build, fails on any warning

OOLD_SCHEMA_DIR=../oold-schema uv run pytest -m parity   # compare against oold-schema's own validator
```

The parity tests skip silently without `OOLD_SCHEMA_DIR`, so a green `make test` does not mean
parity holds. Run them explicitly when touching `src/oold/validation/`.

## Where the details live

This file used to carry the validation subsystem's invariants, the vendoring rules for the
meta-schemas, and this repository's working conventions directly. They now live in the published
docs, redistributed by topic so each is maintained in one place:

- **Validation subsystem design** - the two identifier systems, why severity is read from the
  rule catalogue rather than hardcoded, why a check skips rather than guesses, why checks judge
  the resolved context, why check ids are a public interface, and why this repository and
  oold-schema stay decoupled: [docs/architecture.md, "Validation subsystem design"](docs/architecture.md#validation-subsystem-design).
- **Vendored meta-schemas and fixtures** - byte-exactness, line endings, and how to add a
  version: [docs/maintaining-meta-schemas.md](docs/maintaining-meta-schemas.md).
- **Working conventions** - commit style and releases, no AI attribution, regular dashes, and not
  creating scratch files: [docs/contributing.md, "Conventions"](docs/contributing.md#conventions).
