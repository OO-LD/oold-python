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

## LinkedBaseModel (v1 - legacy)

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

---

## Mapping sets

Reading `x-oold-context` synonyms into an effective `@context`: selecting a mapping set, promoting its synonyms, and resolving a scoped `@context`.

::: oold.utils.mappings

---

## Transformation

Carrying an instance between schemas through RDF, under the `@context` a mapping set selects.

::: oold.utils.transform

---

## Locator

Finding a published schema in a working tree, so a build resolves references offline instead of fetching them.

::: oold.utils.locator

---

## RDF readings

Rendering an instance as Turtle and as a diagram, once per mapping set.

::: oold.utils.readings

---

## SSSOM mapping sets

Bundling the mappings schemas carry inline into SSSOM sets, and chaining two sets into a crosswalk.

::: oold.utils.sssom

---

## Ontology labels

Harvesting human-readable labels for the ontology IRIs a schema maps to, from pinned snapshots.

::: oold.utils.labels

---

## Effective views

Round-tripping an instance under every mapping set its schemas declare, which the declared-context checks cannot see.

::: oold.validation.effective_views
