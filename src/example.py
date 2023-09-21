import oold.model.model as model
from oold.generator import Generator
from oold.model.static import Resolver, ResolveRequest, ResolveResponse

schemas = [
    {
        "id": "Bar",
        "title": "Bar",
        "type": "object",
        "properties": {
            "type": {"type": "array", "items": {"type": "string"}, "default": ["Bar"]},
            "prop1": {"type": "string"},
        },
    },
    {
        "id": "Foo",
        "title": "Foo",
        "type": "object",
        "properties": {
            "type": {"type": "array", "items": {"type": "string"}, "default": ["Foo"]},
            "literal": {"type": "string"},
            "b": {"type": "string", "range": "Bar.json"},
            "b2": {"type": "array", "items": {"type": "string", "range": "Bar.json"}},
        },
    },
]
graph = [
    {"id": "ex:a", "type": ["Foo"], "literal": "test1", "b": "ex:b"},
    {"id": "ex:b", "type": ["Bar"], "prop1": "test2"},
]

g = Generator()
g.generate(schemas)


class MyResolver(Resolver):
    def resolve_iri(self, iri):
        for node in graph:
            if node["id"] == iri:
                cls = node["type"][0]
                entity = eval(f"model.{cls}(**node, resolver=self)")
                return entity

    def resolve(self, request: ResolveRequest):
        print("RESOLVE", request)
        nodes = {}
        for iri in request.iris:
            nodes[iri] = self.resolve_iri(iri)
        return ResolveResponse(nodes=nodes)


r = MyResolver()
f = model.Foo(resolver=r, id="ex:f", b="ex:b", b2=["ex:b", "ex:b"])
print(f.b)
print(f.b.id)
for b in f.b2:
    print(b)
