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
    make docs-test   # strict build - fails on any warning
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

CI will build the package (`uv build`), publish it to PyPI, and deploy the docs to GitHub Pages. The version is derived from the git tag via `hatch-vcs` - no manual version bumping needed.

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

## AI Guidelines

We believe that AI, and in particular LLMs, can be helpful conventional tools to accelerate development and improve quality when used responsibly. AI or any other tool is never the author of code; a human developer always is. Therefore, it is mandatory to carefully review all generated content for correctness, quality, and the absence of legal and ethical issues. For consistency, please avoid patterns that are hard to maintain manually, such as duplicated content or special characters like em dashes or UTF icons.
