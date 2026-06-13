# API Reference

Auto-generated from source docstrings via [mkdocstrings](https://mkdocstrings.github.io/).

---

## GenericLinkedBaseModel

Base class for all linked data models. Provides JSON-LD serialization, type registry, and the `to_jsonld()` / `to_json()` methods.

::: oold.static.GenericLinkedBaseModel

---

## LinkedBaseModel (v2)

Pydantic v2 implementation. Adds IRI-transparent field resolution, lazy loading, `cast()`, and the `[]` subscript operator.

::: oold.model.LinkedBaseModel

---

## BaseController

Mixin for adding runtime behavior to a `LinkedBaseModel` subclass without polluting the data model or the type registry.

::: oold.model.BaseController

---

## LinkedBaseModel (v1 — legacy)

Pydantic v1 implementation. Use `oold.model.LinkedBaseModel` for new projects.

::: oold.model.v1.LinkedBaseModel

---

## Backend interface

Abstract interface implemented by all backends.

::: oold.backend.interface.Backend

---

## Generator

Code generation from OO-LD / JSON Schema definitions.

::: oold.generator.Generator
