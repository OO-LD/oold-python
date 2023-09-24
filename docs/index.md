# Linked Data Classes (oold)

Python toolset for abtract and object oriented access to knowledge graphs. This package aims to implemment this functionality independent from the [osw-python](https://github.com/OpenSemanticLab/osw-python) package.

## Concept

![Concept](./assets/oold_concept.png)

 > Illustrative example how the object orient linked data (OOLD) package provides an abstract knowledge graph (KG) interface. First (line 3) primary schemas (Foo) and their dependencies (Bar, Baz) are loaded from the KG and transformed into python dataclasses. Instantiation of foo is handled by loading the respective JSON(-LD) document from the KG and utilizing the type relation to the corresponding schema and dataclass (line 5). Because bar is not a dependent subobject of foo it is loaded on-demand on first access of the corresponding class attribute of foo (foo.bar in line 7), while id as dependent literal is loaded immediately in the same operation. In line 9 baz is constructed by an existing controller class subclassing Foo and finally stored as a new entity in the KG in line 11.
