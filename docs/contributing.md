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
    uv sync
    uv run pre-commit install
    ```

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
    make docs-test   # strict build — fails on any warning
    ```

=== "without make"

    ```bash
    uv run zensical serve
    uv run zensical build -s
    ```

---

## Releasing

Releases are published automatically by CI when a version tag is pushed.

1. Ensure all changes are merged to `main`
2. Tag the commit and push:

```bash
git tag v0.17.0
git push origin v0.17.0
```

CI will build the package (`uv build`), publish it to PyPI, and deploy the docs to GitHub Pages. The version is derived from the git tag via `hatch-vcs` — no manual version bumping needed.
