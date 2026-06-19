# How to Use

Practical, task-focused guides for every major feature of oold-python. Each one is self-contained - pick the topic you need, or read them in order to build up the full picture.

New here? Start with [Get Started](../get-started.md) to run your first end-to-end example, then come back for the deep dives.

---

## Guides

<div class="grid cards" markdown>

- :material-code-braces:{ .lg .middle } **[Code Generation](codegen.md)**

    ---

    Turn OO-LD / JSON Schema definitions into fully typed Pydantic models - single and multi-schema workflows, schema references, and output model types.

- :material-vector-link:{ .lg .middle } **[Object Graph Mapping](object-graph-mapping.md)**

    ---

    Treat knowledge-graph entities as ordinary Python objects - IRI-transparent fields, lazy resolution across backends, and the `cast()` utility.

- :material-database:{ .lg .middle } **[Backends](backends.md)**

    ---

    Persist and resolve entities anywhere - `SimpleDictDocumentStore`, `SqliteDocumentStore`, `LocalSparqlBackend`, and how to roll your own.

- :material-graph-outline:{ .lg .middle } **[RDF Export](rdf-export.md)**

    ---

    Serialize models to JSON-LD, load them into RDFLib, and query with SPARQL - context injection, cross-object links, and round-trip fidelity.

- :material-tune:{ .lg .middle } **[BaseController](controller.md)**

    ---

    Attach runtime behavior to data models without polluting them - the controller mixin pattern, serialization rules, and multi-model controllers.

</div>
