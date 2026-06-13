# How to Use

Practical guides for every major feature of oold-python. Start with [Get Started](../get-started.md) if you haven't run the first example yet.

---

## Guides

### [Code Generation](codegen.md)

Generate fully typed Pydantic models from OO-LD / JSON Schema definitions. Covers single and multi-schema workflows, schema references, and available output model types.

### [Object Graph Mapping](object-graph-mapping.md)

Work with knowledge graph entities as Python objects. Covers IRI-transparent field assignment, lazy resolution, multiple backends, and the `cast()` conversion utility.

### [Backends](backends.md)

Persist and resolve entities across different storage systems. Covers `SimpleDictDocumentStore`, `SqliteDocumentStore`, `LocalSparqlBackend`, and how to implement a custom backend.

### [RDF Export](rdf-export.md)

Serialize model instances to JSON-LD, load them into an RDFLib graph, and run SPARQL queries. Covers context injection, cross-object linking, and round-trip serialization.

### [BaseController](controller.md)

Add runtime behavior to data models without polluting them. Covers the controller mixin pattern, serialization rules, and multi-model controllers.
