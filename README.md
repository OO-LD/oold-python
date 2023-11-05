[![DOI](https://zenodo.org/badge/691355012.svg)](https://zenodo.org/doi/10.5281/zenodo.8374237)
[![PyPI-Server](https://img.shields.io/pypi/v/oold.svg)](https://pypi.org/project/oold/)
[![Coveralls](https://img.shields.io/coveralls/github/OpenSemanticWorld/oold-python/main.svg)](https://coveralls.io/r/<USER>/oold)
[![Project generated with PyScaffold](https://img.shields.io/badge/-PyScaffold-005CA0?logo=pyscaffold)](https://pyscaffold.org/)


# oold

Linked data class python package for object oriented linked data (OOLD). This package aims to implemment this functionality independent from the [osw-python](https://github.com/OpenSemanticLab/osw-python) package - work in progress.

## Concept

![Concept](./docs/assets/oold_concept.png)

 > Illustrative example how the object orient linked data (OOLD) package provides an abstract knowledge graph (KG) interface. First (line 3) primary schemas (Foo) and their dependencies (Bar, Baz) are loaded from the KG and transformed into python dataclasses. Instantiation of foo is handled by loading the respective JSON(-LD) document from the KG and utilizing the type relation to the corresponding schema and dataclass (line 5). Because bar is not a dependent subobject of foo it is loaded on-demand on first access of the corresponding class attribute of foo (foo.bar in line 7), while id as dependent literal is loaded immediately in the same operation. In line 9 baz is constructed by an existing controller class subclassing Foo and finally stored as a new entity in the KG in line 11.

## Dev
```
git clone https://github.com/OpenSemanticWorld/oold-python
pip install -e .[dev]
```


<!-- pyscaffold-notes -->

## Note

This project has been set up using PyScaffold 4.5. For details and usage
information on PyScaffold see https://pyscaffold.org/.
