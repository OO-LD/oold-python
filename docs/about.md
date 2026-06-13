# About

**oold-python** brings the semantic web into your Python type system. It is the Python implementation of [OO-LD](https://github.com/OO-LD) (Object Oriented Linked Data) - an open community framework that combines JSON Schema and JSON-LD so you can define data structure and semantics in a single source, then reuse that source for validation, RDF generation, code generation, UI generation, and API definitions.

Define schemas once, generate fully typed Pydantic models, resolve objects across knowledge graphs by IRI, and serialize back to JSON-LD - all without leaving familiar Python patterns.

[![DOI](https://zenodo.org/badge/691355012.svg)](https://zenodo.org/doi/10.5281/zenodo.8374237)
[![PyPI](https://img.shields.io/pypi/v/oold.svg)](https://pypi.org/project/oold/)
[![Build](https://img.shields.io/github/actions/workflow/status/OO-LD/oold-python/main.yml?branch=main)](https://github.com/OO-LD/oold-python/actions/workflows/main.yml?query=branch%3Amain)
[![Coverage](https://codecov.io/gh/OO-LD/oold-python/branch/main/graph/badge.svg)](https://codecov.io/gh/OO-LD/oold-python)
[![License](https://img.shields.io/github/license/OO-LD/oold-python)](https://github.com/OO-LD/oold-python/blob/main/LICENSE)

## Why oold-python?

Knowledge graph tools typically force you to choose between semantic richness and developer ergonomics. oold-python bridges that gap:

- **Typed models from schemas** - generate Pydantic dataclasses directly from OO-LD / JSON Schema definitions
- **IRI-transparent references** - fields can hold either a Python object or an IRI string; the library resolves them on demand
- **Pluggable backends** - swap between in-memory dicts, SQLite, local RDF graphs, or live SPARQL endpoints without changing model code
- **Lossless JSON-LD** - serialize any model instance to JSON-LD, preserving the full semantic context
- **Controller pattern** - add runtime behavior (connections, state, archiving) as a mixin without polluting the data model

---

## Quick install

[uv](https://docs.astral.sh/uv/) is the recommended way to install oold-python:

=== "uv (recommended)"

    ```bash
    uv add oold
    ```

=== "pip"

    ```bash
    pip install oold
    ```

---

## First steps

```python
from oold.model import LinkedBaseModel
from pydantic import ConfigDict

class Person(LinkedBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": {"name": "https://schema.org/name"},
            "$id": "https://example.com/Person",
        }
    )
    name: str

alice = Person(name="Alice")
print(alice.to_jsonld())
```

```json
{
  "@context": {"name": "https://schema.org/name"},
  "@type": "https://example.com/Person",
  "name": "Alice"
}
```

---

## Where to go next

<div class="grid cards" markdown>

- :material-rocket-launch:{ .lg .middle } **[Get Started](get-started.md)**

    ---

    Install oold-python and run your first end-to-end example in minutes.

- :material-book-open-variant:{ .lg .middle } **[How to Use](how-to/index.md)**

    ---

    Step-by-step guides for code generation, backends, RDF export, and more.

- :material-layers:{ .lg .middle } **[Architecture](architecture.md)**

    ---

    Understand how the layers fit together - from schemas to SPARQL.

- :material-source-pull:{ .lg .middle } **[Contributing](contributing.md)**

    ---

    Fork, fix, and submit - everything you need to contribute.

</div>

---

## Citation

If you use oold-python in your research, please cite it:

```bibtex
@software{oold_python,
  author  = {OO-LD Contributors},
  title   = {oold-python: Object Oriented Linked Data for Python},
  url     = {https://github.com/OO-LD/oold-python},
  doi     = {10.5281/zenodo.8374237},
}
```

A `CITATION.cff` file is included in the repository - GitHub uses it to populate the **Cite this repository** button on the repo page.

---

## Related work

| Library | Notes |
|---|---|
| [RDFLib](https://github.com/RDFLib/rdflib) | RDF management; no schema validation or type safety. Used as a backend by oold-python. |
| [SuRF](https://github.com/cosminbasca/surfrdf) | ORM-like RDF; dynamically generated classes, no static type checking. |
| [Owlready2](https://github.com/pwin/owlready2) | OWL-aligned classes with native reasoning; no remote SPARQL support. |
| [twa](https://github.com/TheWorldAvatar/baselib/tree/main/python_wrapper) | Pydantic-based OGM; tightly couples RDF properties and type annotations. |
| [COLD](https://github.com/DigiBatt/cold/) | Generates static classes from OWL; no object-to-graph mapping. |

See also: Bai et al. [https://doi.org/10.1039/D5DD00069F](https://doi.org/10.1039/D5DD00069F)
