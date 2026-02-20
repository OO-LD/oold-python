## uv pip install "git+https://github.com/opensemanticworld/panelini.git@add-panel-visnetwork"

import panel as pn
from typing import Any, Dict, List, Optional, Union
from enum import Enum
import pandas as pd
import json
import time

from panelini.panels.visnetwork import GraphDetailTool
from rdflib import Graph as RDFGraph
from rdflib import Node as RDFNode
from rdflib.term import URIRef, Literal
from oold.model import LinkedBaseModel
from pydantic import BaseModel, ConfigDict, Field
from oold.ui.panel import JsonEditor, OoldEditor

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
    def __init__(self, entity_list:List[Entity], edge_label_config: EdgeLabelConfig = "rdf",
                 entity_types: Optional[Dict[str, type]] = None, **kwargs):

        # a dictionary for fast access by iri
        self.entity_list = entity_list
        self.entity_dict = {str(element.get_iri()): element for element in self.entity_list}

        # Store available entity types for creating new entities
        # Default to collecting types from existing entities if not provided
        if entity_types is None:
            self.entity_types = {}
            for entity in entity_list:
                entity_type = type(entity)
                type_name = entity_type.__name__
                if type_name not in self.entity_types:
                    self.entity_types[type_name] = entity_type
        else:
            self.entity_types = entity_types

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
        if current_entity is not None:
            # Display the current entity's properties in a JSON editor for easy editing
            self.current_node_oold_editor = pn.widgets.JSONEditor(
                schema = type(current_entity).export_schema(),
                value=current_entity.model_dump()
            )

            # Store current node ID for the callback
            self._current_single_node_id = node_id

            # Watch for changes in the JSON editor
            self.current_node_oold_editor.param.watch(self.on_single_node_edit, "value")

            #self.current_node_oold_editor = OoldEditor(
            #    oold_model = type(current_entity)
            #)
            self.oold_detail_col.append(self.current_node_oold_editor)
            #time.sleep(2) ## this is weirdly necessary to make sure the editor accepts values
            #self.current_node_oold_editor.value=current_entity.model_dump()

        else:
            # Show UI for creating a new entity
            self.oold_detail_col.append(pn.pane.Markdown("### Create New Entity"))

            if not self.entity_types:
                self.oold_detail_col.append(pn.pane.Markdown("*No entity types available*"))
            else:
                # Dropdown to select entity type
                self.new_entity_type_select = pn.widgets.Select(
                    name="Entity Type",
                    options=list(self.entity_types.keys()),
                    value=list(self.entity_types.keys())[0],
                    width=200
                )

                # Confirm button
                self.new_entity_confirm_button = pn.widgets.Button(
                    name="Create Entity",
                    button_type="success",
                    width=150
                )
                self.new_entity_confirm_button.on_click(self.on_create_entity_click)

                # Store the node_id for later use
                self._new_entity_node_id = node_id

                # Add UI elements
                self.oold_detail_col.append(
                    pn.Row(self.new_entity_type_select, self.new_entity_confirm_button)
                )

        self.detail_tabs.active = 2 # switch to the OO-LD details tab

    # ===== Multi-Node Comparison Functionality =====

    def show_multi_node_editor(self, node_ids: List[Any]) -> None:
        """Override to show OO-LD-aware multi-node comparison tables.

        Displays two comparison tables in the OO-LD Details tab:
        1. Comparison table for editing individual entity properties
        2. Set-all table for bulk editing all selected entities

        Args:
            node_ids: List of node IDs (IRIs) to compare
        """
        # Let parent handle visual properties in Details tab
        super().show_multi_node_editor(node_ids)

        # Now populate OO-LD Details tab with semantic properties
        self.oold_detail_col.clear()
        self.oold_detail_col.append(
            pn.pane.Markdown(f"### OO-LD Multi-Node Editor ({len(node_ids)} nodes)")
        )

        # Get entities
        selected_entities = [self.entity_dict[nid] for nid in node_ids if nid in self.entity_dict]

        if not selected_entities:
            self.oold_detail_col.append(pn.pane.Markdown("*No entities found for selected nodes*"))
            return

        # Find common properties
        common_props = self._get_common_properties(selected_entities)

        if not common_props:
            self.oold_detail_col.append(pn.pane.Markdown("*No common properties found*"))
            return

        # Build comparison DataFrame
        comp_df = self._build_comparison_dataframe(selected_entities, common_props)

        # Build editor configs
        editors = {"_iri": None}  # IRI column not editable
        for prop in common_props:
            editors[prop] = self._get_property_editor_config(selected_entities[0], prop)

        # Create comparison tabulator
        self.oold_detail_col.append(pn.pane.Markdown("#### Property Comparison Table"))
        self.oold_detail_col.append(pn.pane.Markdown("*Edit cells to update individual entities*"))

        self.oold_comparison_tabulator = pn.widgets.Tabulator(
            comp_df,
            editors=editors,
            hidden_columns=["_iri"],  # Hide IRI column
            width=700,
            height=min(400, 50 + len(node_ids) * 30),
        )
        self.oold_comparison_tabulator.on_edit(self.on_oold_tabulator_cell_edit)
        self.oold_detail_col.append(self.oold_comparison_tabulator)

        # Build set-all table
        self.oold_detail_col.append(pn.pane.Markdown("#### Set Value for All Selected Entities"))
        self.oold_detail_col.append(pn.pane.Markdown("*Edit cells to apply value to ALL selected entities*"))

        table_data = comp_df.to_dict('records')
        set_all_row = self._build_set_all_row(table_data, common_props)
        set_all_df = pd.DataFrame([set_all_row])

        self.oold_set_all_tabulator = pn.widgets.Tabulator(
            set_all_df,
            editors=editors,
            width=700,
            height=100,
        )
        self.oold_set_all_tabulator.on_edit(self.on_oold_set_all_cell_edit)
        self.oold_detail_col.append(self.oold_set_all_tabulator)

        # Store selected IDs for callbacks
        self._current_selected_node_ids = node_ids

        # Switch to OO-LD Details tab
        self.detail_tabs.active = 2

    # ===== Property Introspection Helpers =====

    def _get_common_properties(self, entities: List[LinkedBaseModel]) -> List[str]:
        """Find properties common to all selected entities.

        Args:
            entities: List of LinkedBaseModel instances

        Returns:
            Sorted list of property names that exist on all entities
        """
        if not entities:
            return []

        # Get model fields from first entity as baseline
        first_model_fields = set(entities[0].model_fields.keys())

        # Find intersection across all entities
        common_fields = first_model_fields.copy()
        for entity in entities[1:]:
            entity_fields = set(entity.model_fields.keys())
            common_fields &= entity_fields

        # Filter out internal/system fields
        exclude_fields = {'id', 'type', '__iris__'}
        common_fields -= exclude_fields

        # Prioritize 'name' and 'label' to appear first
        priority_fields = ['name', 'label']
        result = []

        # Add priority fields first (if they exist)
        for field in priority_fields:
            if field in common_fields:
                result.append(field)
                common_fields.remove(field)

        # Add remaining fields in sorted order
        result.extend(sorted(common_fields))

        return result

    def _get_property_editor_config(self, entity: LinkedBaseModel, prop_name: str) -> Dict[str, Any]:
        """Get Tabulator editor configuration for a property.

        Args:
            entity: Sample entity to inspect
            prop_name: Name of the property

        Returns:
            Dict with 'type' and optionally 'values' for editor config
        """
        field = entity.model_fields[prop_name]
        annotation = field.annotation

        # Handle Optional/Union types
        origin = getattr(annotation, '__origin__', None)
        if origin is Union:
            non_none = [t for t in annotation.__args__ if t is not type(None)]
            if non_none:
                annotation = non_none[0]
                origin = getattr(annotation, '__origin__', None)

        # Check for Enum
        try:
            if isinstance(annotation, type) and issubclass(annotation, Enum):
                return {
                    "type": "list",
                    "values": [e.value for e in annotation]
                }
        except TypeError:
            pass

        # Check for List
        if origin is list:
            return {"type": "input"}  # JSON string input for lists

        # Primitive types
        if annotation in (int, float):
            return {"type": "number"}
        elif annotation is bool:
            return {"type": "tickCross"}
        else:
            return {"type": "input"}  # Default to text input

    def _serialize_property_value(self, value: Any) -> Any:
        """Serialize a property value for display in tabulator.

        Handles enums, lists, and other complex types.

        Args:
            value: Property value from entity

        Returns:
            Serialized value suitable for tabulator display
        """
        if value is None:
            return None
        elif isinstance(value, Enum):
            return value.value
        elif isinstance(value, list):
            if all(isinstance(v, str) for v in value):
                return json.dumps(value)  # List of strings/IRIs
            elif all(isinstance(v, Enum) for v in value):
                return json.dumps([v.value for v in value])
            else:
                return json.dumps([str(v) for v in value])
        elif isinstance(value, (str, int, float, bool)):
            return value
        else:
            return str(value)

    def _deserialize_property_value(self, entity: LinkedBaseModel, prop_name: str, value: Any) -> Any:
        """Deserialize a tabulator value back to property type.

        Handles type conversion, enums, and lists.

        Args:
            entity: Entity to update
            prop_name: Property name
            value: Value from tabulator

        Returns:
            Deserialized value suitable for entity assignment
        """
        field = entity.model_fields[prop_name]
        annotation = field.annotation

        # Handle Optional types
        origin = getattr(annotation, '__origin__', None)
        args = getattr(annotation, '__args__', ())

        if origin is Union:
            # Filter out NoneType
            non_none_types = [t for t in args if t is not type(None)]
            if non_none_types:
                annotation = non_none_types[0]
                origin = getattr(annotation, '__origin__', None)
                args = getattr(annotation, '__args__', ())

        # Handle List types
        if origin is list:
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        # Check if list of enums
                        if args:
                            try:
                                if issubclass(args[0], Enum):
                                    return [args[0](v) for v in parsed]
                            except TypeError:
                                pass
                        return parsed
                except (json.JSONDecodeError, ValueError):
                    pass
            return value

        # Handle Enum types
        try:
            if isinstance(annotation, type) and issubclass(annotation, Enum):
                return annotation(value)
        except TypeError:
            pass

        # Handle primitives
        if annotation in (int, float, bool, str):
            if value == "" or value is None:
                return None
            return annotation(value)

        return value

    # ===== Table Building =====

    def _build_comparison_dataframe(self, entities: List[LinkedBaseModel], properties: List[str]) -> pd.DataFrame:
        """Build DataFrame for comparison table.

        Args:
            entities: List of entities to compare
            properties: List of property names to include

        Returns:
            DataFrame with one row per entity
        """
        rows = []
        for entity in entities:
            row = {"_iri": str(entity.get_iri())}  # Hidden column for callbacks

            # Use model_dump to get serialized values (avoids lazy resolution)
            entity_dict = entity.model_dump()

            for prop in properties:
                # Get value from the dumped dict to avoid triggering __getattribute__ resolution
                value = entity_dict.get(prop, None)
                row[prop] = self._serialize_property_value(value)
            rows.append(row)

        return pd.DataFrame(rows)

    def _build_set_all_row(self, table_data: List[Dict[str, Any]], properties: List[str]) -> Dict[str, Any]:
        """Build single row for set-all table showing common values.

        Args:
            table_data: List of row dicts from comparison table
            properties: List of property names

        Returns:
            Dict with common values or empty/None for differing values
        """
        set_all_row = {}

        # Always include _iri as None (not editable)
        set_all_row["_iri"] = None

        for prop in properties:
            values = [row[prop] for row in table_data]
            first_val = values[0]

            # Check if all values are the same
            if all(v == first_val for v in values):
                set_all_row[prop] = first_val
            else:
                # Values differ - show empty for better UX
                set_all_row[prop] = "" if isinstance(first_val, str) else None

        return set_all_row

    def _refresh_oold_tabulators(self) -> None:
        """Refresh OO-LD comparison and set-all tables with current entity data."""
        if not hasattr(self, 'oold_comparison_tabulator') or not hasattr(self, 'oold_set_all_tabulator'):
            return

        # Get current selected entities
        selected_entities = [
            self.entity_dict[nid] for nid in self._current_selected_node_ids
            if nid in self.entity_dict
        ]

        if not selected_entities:
            return

        # Get common properties
        common_props = self._get_common_properties(selected_entities)

        if not common_props:
            return

        # Rebuild comparison DataFrame
        comp_df = self._build_comparison_dataframe(selected_entities, common_props)
        self.oold_comparison_tabulator.value = comp_df

        # Rebuild set-all row
        table_data = comp_df.to_dict('records')
        set_all_row = self._build_set_all_row(table_data, common_props)
        set_all_df = pd.DataFrame([set_all_row])
        self.oold_set_all_tabulator.value = set_all_df

    # ===== Synchronization =====

    def _rebuild_rdf_graph(self) -> None:
        """Rebuild RDF graph from all entities in entity_list."""
        self.rdf_graph = RDFGraph()
        for entity in self.entity_list:
            self.rdf_graph.parse(data=entity.to_jsonld(), format="json-ld")

    def _rebuild_visjs_edges(self) -> None:
        """Rebuild visjs edges from RDF graph.

        Preserves nodes, rebuilds edges based on current entity relationships.
        """
        self.visjs_edges = []
        available_ids = set(node["id"] for node in self.visjs_nodes)

        for s, p, o in self.rdf_graph:
            if str(s) in available_ids:
                self.visjs_edges.append({
                    "from": str(s),
                    "to": str(o),
                    "label": str(p.split("/")[-1].split("#")[-1]),
                    "arrows": "to",
                })

    def _sync_entity_to_visjs(self, entity: LinkedBaseModel) -> None:
        """Sync a single entity's data to its corresponding visjs node.

        Updates node label if entity.name changed.

        Args:
            entity: The updated entity
        """
        iri = str(entity.get_iri())
        for node in self.visjs_nodes:
            if node["id"] == iri:
                if hasattr(entity, "name"):
                    node["label"] = entity.name
                break

    def _full_sync_after_edit(self) -> None:
        """Perform full sync of all data structures after entity edit.

        Ensures consistency between LinkedBaseModel instances, RDF graph,
        and visualization (nodes and edges).
        """
        # Rebuild RDF graph
        self._rebuild_rdf_graph()

        # Rebuild edges
        self._rebuild_visjs_edges()

        # Sync node labels
        for entity in self.entity_list:
            self._sync_entity_to_visjs(entity)

        # Update visnetwork (triggers Panel update)
        self.visnetwork_panel.nodes = self.visjs_nodes
        self.visnetwork_panel.edges = self.visjs_edges

        # Refresh tables if displayed
        if hasattr(self, 'oold_comparison_tabulator'):
            self._refresh_oold_tabulators()

    # ===== Event Handlers =====

    def on_oold_tabulator_cell_edit(self, event: Any) -> None:
        """Callback when a cell is edited in the OO-LD comparison table.

        Updates the specific entity and syncs all data structures.

        Args:
            event: Panel event with row, column, value
        """
        try:
            row_index = event.row
            column = event.column
            value = event.value

            # Get entity IRI from hidden column
            row_data = self.oold_comparison_tabulator.value.iloc[row_index]
            entity_iri = row_data["_iri"]

            # Get entity
            entity = self.entity_dict[entity_iri]

            # Deserialize and set property
            deserialized = self._deserialize_property_value(entity, column, value)
            setattr(entity, column, deserialized)

            print(f"Updated {entity_iri} property '{column}' to: {deserialized}")

            # Full sync
            self._full_sync_after_edit()

        except Exception as e:
            print(f"Error updating entity: {e}")
            import traceback
            traceback.print_exc()
            # Revert to current state
            self._refresh_oold_tabulators()

    def on_oold_set_all_cell_edit(self, event: Any) -> None:
        """Callback when a cell is edited in the OO-LD set-all table.

        Updates ALL selected entities and syncs all data structures.

        Args:
            event: Panel event with column, value
        """
        try:
            column = event.column
            value = event.value

            print(f"Setting property '{column}' to '{value}' for all selected entities")

            # Update all selected entities
            for node_id in self._current_selected_node_ids:
                if node_id in self.entity_dict:
                    entity = self.entity_dict[node_id]
                    deserialized = self._deserialize_property_value(entity, column, value)
                    setattr(entity, column, deserialized)
                    print(f"  Updated {node_id}")

            # Full sync
            self._full_sync_after_edit()

        except Exception as e:
            print(f"Error updating entities: {e}")
            import traceback
            traceback.print_exc()
            # Revert to current state
            self._refresh_oold_tabulators()

    def on_single_node_edit(self, event: Any) -> None:
        """Callback when the single-node JSON editor is modified.

        Updates the entity from the edited JSON and syncs all data structures.

        Args:
            event: Panel parameter event with new value
        """
        try:
            if not hasattr(self, '_current_single_node_id'):
                return

            node_id = self._current_single_node_id
            new_value_dict = event.new

            if node_id not in self.entity_dict:
                print(f"Warning: Entity {node_id} not found in entity_dict")
                return

            entity = self.entity_dict[node_id]

            print(f"Updating entity {node_id} from JSON editor")

            # Update each property from the edited JSON
            for prop_name, prop_value in new_value_dict.items():
                # Skip internal fields
                if prop_name in ['id', '__iris__']:
                    continue

                # Check if property exists in model
                if prop_name in entity.model_fields:
                    try:
                        # Deserialize the value to the correct type
                        deserialized = self._deserialize_property_value(entity, prop_name, prop_value)
                        setattr(entity, prop_name, deserialized)
                        print(f"  Updated property '{prop_name}' to: {deserialized}")
                    except Exception as e:
                        print(f"  Warning: Could not update property '{prop_name}': {e}")

            # Full sync to update all data structures
            self._full_sync_after_edit()

        except Exception as e:
            print(f"Error in single node edit: {e}")
            import traceback
            traceback.print_exc()

    def on_create_entity_click(self, event: Any) -> None:
        """Callback when the 'Create Entity' button is clicked.

        Shows a JSON editor for creating a new entity of the selected type.

        Args:
            event: Button click event
        """
        try:
            if not hasattr(self, 'new_entity_type_select') or not hasattr(self, '_new_entity_node_id'):
                return

            # Get selected entity type
            entity_type_name = self.new_entity_type_select.value
            entity_type = self.entity_types[entity_type_name]

            # Clear the column and show editor
            self.oold_detail_col.clear()
            self.oold_detail_col.append(pn.pane.Markdown(f"### Create New {entity_type_name}"))

            # Create a default instance with minimal required fields
            # Start with just name for most entities
            default_values = {}

            # Check if 'name' field exists and add a default
            if 'name' in entity_type.model_fields:
                default_values['name'] = f"New{entity_type_name}"

            # Create JSON editor with schema
            self.new_entity_editor = pn.widgets.JSONEditor(
                value=default_values,
                schema=entity_type.export_schema(),
                width=700,
                height=500
            )

            # Save button
            self.new_entity_save_button = pn.widgets.Button(
                name="Save Entity",
                button_type="primary",
                width=150
            )
            self.new_entity_save_button.on_click(self.on_new_entity_save)

            # Cancel button
            self.new_entity_cancel_button = pn.widgets.Button(
                name="Cancel",
                button_type="default",
                width=150
            )
            self.new_entity_cancel_button.on_click(self.on_new_entity_cancel)

            # Store entity type for save handler
            self._new_entity_type = entity_type

            # Add UI elements
            self.oold_detail_col.append(self.new_entity_editor)
            self.oold_detail_col.append(
                pn.Row(self.new_entity_save_button, self.new_entity_cancel_button)
            )

        except Exception as e:
            print(f"Error creating entity editor: {e}")
            import traceback
            traceback.print_exc()
            self.oold_detail_col.append(pn.pane.Markdown(f"*Error: {e}*"))

    def on_new_entity_save(self, event: Any) -> None:
        """Callback when the 'Save Entity' button is clicked.

        Creates the new entity, adds it to all data structures, and updates the visualization.

        Args:
            event: Button click event
        """
        try:
            if not hasattr(self, 'new_entity_editor') or not hasattr(self, '_new_entity_type'):
                return

            # Get the entity data from editor
            entity_data = self.new_entity_editor.value
            entity_type = self._new_entity_type

            print(f"Creating new entity of type {entity_type.__name__}: {entity_data}")

            # Create the entity instance
            new_entity = entity_type(**entity_data)
            entity_iri = str(new_entity.get_iri())

            # Add to entity_list and entity_dict
            self.entity_list.append(new_entity)
            self.entity_dict[entity_iri] = new_entity

            # Create visjs node for the new entity
            node_label = entity_data.get('name', entity_iri)
            new_visjs_node = {
                "id": entity_iri,
                "label": node_label,
                "shape": "ellipse",
            }
            self.visjs_nodes.append(new_visjs_node)

            print(f"Created new entity with IRI: {entity_iri}")

            # Full sync to update RDF graph and edges
            self._full_sync_after_edit()

            # Clear the creation UI and show success message
            self.oold_detail_col.clear()
            self.oold_detail_col.append(
                pn.pane.Markdown(f"### ✓ Entity Created Successfully\n\nIRI: `{entity_iri}`")
            )
            self.oold_detail_col.append(
                pn.pane.Markdown(f"The new {entity_type.__name__} has been added to the graph.")
            )

        except Exception as e:
            print(f"Error saving new entity: {e}")
            import traceback
            traceback.print_exc()
            self.oold_detail_col.clear()
            self.oold_detail_col.append(
                pn.pane.Markdown(f"### Error Creating Entity\n\n```\n{str(e)}\n```")
            )

    def on_new_entity_cancel(self, event: Any) -> None:
        """Callback when the 'Cancel' button is clicked during entity creation.

        Clears the creation UI.

        Args:
            event: Button click event
        """
        self.oold_detail_col.clear()
        self.oold_detail_col.append(
            pn.pane.Markdown("### Entity creation cancelled")
        )


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
                    "age": {
                        "@id": "ex:HasAge"
                    }
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
    age: Optional[int] = Field(
        None,
        description="Age of the person",
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

    # Define available entity types for creation
    available_entity_types = {
        "Person": Person,
        "Entity": Entity,
    }

    # build graph tool and show it
    graph_detail_panel = OOLDGraphDetailTool(
        entity_list=example_oold_list,
        entity_types=available_entity_types
    )
    pn.serve(graph_detail_panel, threaded=True)
