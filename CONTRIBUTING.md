# Contributing

Contributions are welcome! You can help by reporting bugs, implementing features, or improving documentation. File issues and PRs at [github.com/OO-LD/oold-python](https://github.com/OO-LD/oold-python).

## Development Setup

Requires `uv` and `git`.

```bash
git clone git@github.com:YOUR_NAME/oold-python.git
cd oold-python
uv sync
uv run pre-commit install
```

## Making Changes

1. Create a branch: `git checkout -b name-of-your-fix`
2. Make your changes and add tests in `tests/`
3. Run checks and tests (see below)
4. Commit and push, then open a pull request

### With `make`

```bash
make check   # lint, type-check, dependency audit
make test    # pytest with coverage
```

### Without `make`

```bash
uv lock --locked
uv run pre-commit run -a
uv run ty check
uv run deptry src
uv run python -m pytest --cov --cov-config=pyproject.toml --cov-report=xml
```

## Releasing

Releases are published automatically by CI when a version tag is pushed.

1. Ensure all changes are merged to `main`
2. Tag the commit and push:

   ```bash
   git tag v0.17.0
   git push origin v0.17.0
   ```

CI will build the package (`uv build`), publish it to PyPI, and deploy the docs to GitHub Pages. The version is derived from the git tag via `hatch-vcs` — no manual version bumping needed.
