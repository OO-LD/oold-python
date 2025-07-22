[![DOI](https://zenodo.org/badge/691355012.svg)](https://zenodo.org/doi/10.5281/zenodo.8374237)
[![PyPI-Server](https://img.shields.io/pypi/v/oold.svg)](https://pypi.org/project/oold/)
[![Coveralls](https://img.shields.io/coveralls/github/OpenSemanticWorld/oold-python/main.svg)](https://coveralls.io/r/<USER>/oold)
[![Project generated with PyScaffold](https://img.shields.io/badge/-PyScaffold-005CA0?logo=pyscaffold)](https://pyscaffold.org/)


# oold-python

Linked data class python package for object oriented linked data ([OO-LD](https://github.com/OO-LD/schema)) based on [pydantic](https://github.com/pydantic/pydantic). This package aims to implemment this functionality independent from the [osw-python](https://github.com/OpenSemanticLab/osw-python) package - work in progress.

## Installation
```
pip install oold
```

## Objectives
- lossless transpilation between [OO-LD](https://github.com/OO-LD/schema) schemas and extended pydantic data classes
- interprete string IRIs with `oold-range` annotation as typed class property
- dynamically resolve such IRIs from one or multiple backends (simple in-memory dict, RDF-Graph, SPARQL-Endpoint, Document Store, etc.)
- serialized class instances to JSON-LD while replacing python object-references with IRIs
- apply filters / queries to backend-requests (SPARQL, GraphQL, ...)

## Related Work

| **Lib Name** | **Repo**                                                                                     | **Description**                                                                                                                                                                    |
|--------------|----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **RDFLib**   | [https://github.com/RDFLib/rdflib](https://github.com/RDFLib/rdflib)                         | Widely used for managing RDF data; lacks built-in schema validation or type safety, requires external reasoning tools. Provides local/remote SPARQL support (used as backend for oold-python).  |
| **SuRF**     | [https://github.com/cosminbasca/surfrdf](https://github.com/cosminbasca/surfrdf)             | ORM-like approach for RDF; Dynamically generated class definitions, no static type checking.                                                                                                    |
| **Owlready2**| [https://github.com/pwin/owlready2](https://github.com/pwin/owlready2)                       | Provides Python classes aligned with OWL and includes native reasoning (HermiT/Pellet). Limited runtime type validation; no direct remote SPARQL endpoint support.                              |
| **twa**      | [https://github.com/TheWorldAvatar/baselib/tree/main/python_wrapper](https://github.com/TheWorldAvatar/baselib/tree/main/python_wrapper) | Pydantic-based OGM with built-in schema validation/type safety; Strong coupling of RDF-Properties and type annotations.                             |
| **COLD**     | [https://github.com/DigiBatt/cold/](https://github.com/DigiBatt/cold/)                       | Generates static python classes from OWL classes to offer RDF generation. No object-to-graph mapping                                                                                            |

see also Bai et al. https://doi.org/10.1039/D5DD00069F


## Features

### Code Generation
Generate Python data models from OO-LD Schemas (based on [datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator)):

```python
from oold.generator import Generator
import importlib
import datamodel_code_generator
import oold.model.model as model

schemas = [
    {   # minimal example
        "id": "Foo",
        "title": "Foo",
        "type": "object",
        "properties": {
            "id": {"type": "string"},
        },
    },
]
g = Generator()
g.generate(schemas, main_schema="Foo.json", output_model_type=datamodel_code_generator.DataModelType.PydanticBaseModel)
importlib.reload(model)

# Now you can work with your generated model
f = model.Foo(id="ex:f")
print(f)
```

This example uses the built-in `Generator` to create a basic Pydantic model (v1 or v2) from JSON schemas.

More details see [example code](./tests/test_oold.py)

### Object Graph Mapping

![Concept](./docs/assets/oold_concept.png)

 > Illustrative example how the object orient linked data (OO-LD) package provides an abstract knowledge graph (KG) interface. First (line 3) primary schemas (Foo) and their dependencies (Bar, Baz) are loaded from the KG and transformed into python dataclasses. Instantiation of foo is handled by loading the respective JSON(-LD) document from the KG and utilizing the type relation to the corresponding schema and dataclass (line 5). Because bar is not a dependent subobject of foo it is loaded on-demand on first access of the corresponding class attribute of foo (foo.bar in line 7), while id as dependent literal is loaded immediately in the same operation. In line 9 baz is constructed by an existing controller class subclassing Foo and finally stored as a new entity in the KG in line 11.

Represent your domain objects easily and reference them via IRIs or direct object instances. For instance, if you have a `Foo` model referencing a `Bar` model:

```python
import oold.model.model as model

# Create a Foo object linked to Bar
f = model.Foo(
    id="ex:f",
    literal="test1",
    b=model.Bar(id="ex:b", prop1="test2"),
    b2=[model.Bar(id="ex:b1", prop1="test3"), model.Bar(id="ex:b2", prop1="test4")],
)

print(f.b.id)          # ex:b
print(f.b2[0].prop1)   # test3
```

You can also refer to objects by IRI:

```python
# Assign IRI strings directly
f = model.Foo(
    id="ex:f",
    literal="test1",
    b="ex:b",  # automatically resolved to a Bar object
    b2=["ex:b1", "ex:b2"],
)
```

Thanks to the resolver mechanism, these IRIs turn into fully-fledged objects as soon as you need them.

More details see [example code](./tests/test_oold.py)

### RDF-Export
Easily convert your objects to RDF (JSON-LD) and integrate with SPARQL queries:

```python
from rdflib import Graph
from typing import List, Optional

# Example: Convert Person objects to RDF
p1 = model.Person(name="Alice")
p2 = model.Person(name="Bob", knows=[p1])

# Export to JSON-LD
print(p2.to_jsonld())

# Load into RDFlib
g = Graph()
g.parse(data=p1.to_jsonld(), format="json-ld")
g.parse(data=p2.to_jsonld(), format="json-ld")

# Perform SPARQL queries
qres = g.query("""
    SELECT ?name
    WHERE {
        ?s <https://schema.org/knows> ?o .
        ?o <https://schema.org/name> ?name .
    }
""")
for row in qres:
    print("Bob knows", row.name)
```

The extended dataclass notation includes semantic annotations as JSON-LD context, giving you powerful tooling for knowledge graphs, semantic queries, and data interoperability.

More details see [example code](./tests/test_rdf.py)

## Dev
```
git clone https://github.com/OpenSemanticWorld/oold-python
pip install -e .[dev]
```


<!-- pyscaffold-notes -->

## Note

This project has been set up using PyScaffold 4.5. For details and usage
information on PyScaffold see https://pyscaffold.org/.
