# Development

This project uses [uv](https://docs.astral.sh/uv/) for environment/dependency
management and `make` as the developer entrypoint.

## Setup

Install the virtual environment and the pre-commit hooks:

```bash
make install
```

(equivalent to `uv sync` + `uv run pre-commit install`)

## Code quality

Run the linters, formatter, type checker and dependency check:

```bash
make check
```

(`pre-commit` / ruff, `ty check`, `deptry`)

## Testing

1. Create a new test (file name `test_*.py`) under `/tests`.
2. Run the test suite:

```bash
make test
```

To run the suite across all supported Python versions:

```bash
uv run tox
```

## Benchmarks

```bash
make benchmark
```

## Documentation

Build and serve the docs locally with [zensical](https://github.com/squidfunk/zensical):

```bash
make docs        # serve with live reload
make docs-test   # strict build (fails on warnings)
```
