## uv pip install "git+https://github.com/opensemanticworld/panelini.git@add-panel-visnetwork"

import panel as pn
from typing import Any
from enum import Enum

from panelini.panels.visnetwork import GraphDetailTool
from rdflib import Graph as RDFGraph
from rdflib import Node as RDFNode
from rdflib.term import URIRef, Literal
from oold.model import LinkedBaseModel
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from oold.ui.panel import JsonEditor, OoldEditor
import time
import json

pn.extension("tabulator")  # For tables
pn.extension("jsoneditor")  # For viewing/editing node details

class Entity(LinkedBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": {
                # aliases
                "id": "@id",
                "type": "@type",
                # prefixes
                "schema": "https://schema.org/",
                "ex": "https://example.com/",
                # literal property
                "name": "schema:name",
            },
            "iri": "Entity.json",  # the IRI of the schema
        }
    )
    type: Optional[str] = Field(
        "ex:Entity.json",
        json_schema_extra={"options": {"hidden": "true"}},
    )
    name: str

    def get_iri(self):
        return "https://example.com/" + self.name


class OOLDGraph(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity.json",  # import the context of the parent class
                {
                    # object property definition
                    "object_list": {
                        "@id": "ex:HasPart",
                        "@type": "@id",
                    },
                },
            ],
            "iri": "OOLDGraph.json",
            "defaultProperties": ["object_list"],
        }
    )
    object_list: List[Entity]

class EdgeLabelConfig(Enum):
    """Configuration options for edge labels in the graph visualization."""

    RDF = "rdf"
    """Use RDF predicates as edge labels."""

    JSON_KEYS = "json_keys" ## in implementation use json-ld @vobab
    """Use custom labels defined in the data model or visualization configuration."""


class OOLDGraphDetailTool(GraphDetailTool):
    def __init__(self, entity_list:List[Entity], edge_label_config: EdgeLabelConfig = "rdf", **kwargs):

        # a dictionary for fast access by iri
        self.entity_list = entity_list
        self.entity_dict = {str(element.get_iri()): element for element in self.entity_list}

        self.rdf_graph = RDFGraph()

        for element in self.entity_list:
            self.rdf_graph.parse(data=element.to_jsonld(), format="json-ld")  ## appends elements

        ### transform python-classes/instances to visjs nodes/edges
        ## iterate over all triples
        ## for each triple:
        ## * create an edge with the predicate as label and the subject and object as source and target
        ## * create nodes for the subject and object if they don't exist yet, with the label as the name of the entity (e.g. name property) or the IRI if no name is available
        ## ids shall be iris

        self.visjs_nodes = []
        self.visjs_edges = []

        show_literals = False
        show_whole_graph = False

        def add_node_by_id(id_str: str):
            id_str = str(id_str)
            oold_obj = self.entity_dict.get(id_str, id_str)

            if oold_obj is not None:

                if hasattr(oold_obj, "name"):
                    label = oold_obj.name
                else:
                    label = id_str

                visjs_node = {
                    "id": id_str,
                    "label": label,
                    "shape": "ellipse",
                }
                self.visjs_nodes.append(visjs_node)
            else:
                print(f"Warning: IRI {id} not found in self.entity_dict")

        def iri_to_edge_label(iri: URIRef) -> str:
            # simple implementation: take the last part of the IRI after the last slash or hash
            return iri.split("/")[-1].split("#")[-1]

        ## build graph from all rdf triples, except for literals
        if show_whole_graph:
            for s, p, o in self.rdf_graph:
                # create edge

                if isinstance(o, URIRef) or show_literals:

                    self.visjs_edges.append({
                        "from": str(s),
                        "to": str(o),
                        "label": iri_to_edge_label(p),
                    })
                    # create nodes if they don't exist yet

                    if not any(node["id"] == str(s) for node in self.visjs_nodes):
                        add_node_by_id(str(s))

                    if not any(node["id"] == str(o) for node in self.visjs_nodes):
                        add_node_by_id(str(o))

        ## build graph from nodes and their relations:

        for id_str, element in self.entity_dict.items():
            # create node
            add_node_by_id(id_str)

        ## add all edges between the nodes based on the relations in the OO-LD objects
        available_ids = set(node["id"] for node in self.visjs_nodes)
        for s, p, o in self.rdf_graph:
            if str(s) in available_ids:
                self.visjs_edges.append({
                    "from": str(s),
                    "to": str(o),
                    "label": str(p.split("/")[-1].split("#")[-1]),
                    "arrows": "to",
                })

        super().__init__(nodes=self.visjs_nodes, edges=self.visjs_edges)
        self.oold_detail_col = pn.Column()
        self.detail_tabs.append(("OO-LD Details", self.oold_detail_col))

    def show_node_details(self, node_id: Any) -> None:
        """Override the method to show node details in the side panel in a OO-LD-specific fashion"""

        super().show_node_details(node_id)

        self.oold_detail_col.clear()
        self.oold_detail_col.append(pn.pane.Markdown(f"### Node ID: {node_id} of type "
                                                     f"{type(self.entity_dict.get(node_id)).__name__}"))

        current_entity = self.entity_dict.get(node_id, None)

        self.current_node_oold_editor = pn.widgets.JSONEditor(
            value=current_entity.model_dump()
        )

        #self.current_node_oold_editor = OoldEditor(
        #    oold_model = type(current_entity)
        #)
        self.oold_detail_col.append(self.current_node_oold_editor)
        #time.sleep(2) ## this is weirdly necessary to make sure the editor accepts values
        #self.current_node_oold_editor.value=current_entity.model_dump()

        self.detail_tabs.active = 2 # switch to the OO-LD details tab


class Hobby(str, Enum):
    """Various hobbies as an enum."""

    SPORTS = "ex:sports"
    """Sports hobby, e.g. football, basketball, etc."""
    MUSIC = "ex:music"
    """Music hobby, e.g. playing instruments, singing, etc."""
    ART = "ex:art"
    """Art hobby, e.g. painting, drawing, etc."""


class Person(Entity):
    """A simple Person schema"""

    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity.json",  # import the context of the parent class
                {
                    # object property definition
                    "hobbies": {
                        "@id": "ex:hobbies",
                        "@type": "@id",
                    },
                    "knows": {
                        "@id": "schema:knows",
                        "@type": "@id",
                        "@container": "@set",
                    },
                },
            ],
            "iri": "Person.json",
            "defaultProperties": ["type", "name", "hobbies"],
        }
    )
    type: Optional[str] = "ex:Person.json"
    hobbies: Optional[List[Hobby]] = None
    """interests of the person, e.g. sports, music, art"""
    knows: Optional[List["Person"]] = Field(
        None,
        # object property pointing to another Person
        json_schema_extra={"range": "Person.json"},
    )
if __name__ == "__main__":

    ## a list of OO-LD objects
    from oold.model import LinkedBaseModel
    from enum import Enum
    from typing import List, Optional, Any
    from pydantic import Field, ConfigDict





    alice = Person(name="Alice", hobbies=[Hobby.SPORTS, Hobby.MUSIC])
    bob = Person(name="Bob", hobbies=[Hobby.ART], knows=[alice])
    charlie = Person(name="Charlie", hobbies=[Hobby.SPORTS], knows=[alice, bob])
    david = Person(name="David", hobbies=[Hobby.MUSIC], knows=[charlie])
    eve = Person(name="Eve", hobbies=[Hobby.ART, Hobby.MUSIC], knows=[david, alice, bob])
    alice.knows = [bob.get_iri(), charlie.get_iri(), eve.get_iri()]

    example_oold_list =[
            alice, bob, charlie, david, eve
    ]

    # build graph tool and show it
    graph_detail_panel = OOLDGraphDetailTool(entity_list=example_oold_list)
    pn.serve(graph_detail_panel, threaded=True)
