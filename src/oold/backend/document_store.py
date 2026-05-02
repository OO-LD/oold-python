import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from oold.backend.interface import (
    Backend,
    Condition,
    LinkedDataFormat,
    Query,
    QueryParam,
    ResolveParam,
    ResolveResult,
    StoreResult,
    apply_operator,
)


class SimpleDictDocumentStore(Backend):
    """In-memory document store backed by a Python dict.

    Optionally persists to a JSON file if ``file_path`` is set.
    On init, loads existing data from the file (if it exists).
    On every store, writes the full dict back to disk.
    """

    _store: Optional[Dict[str, dict]] = None
    file_path: Optional[Union[Path, str]] = None
    format: LinkedDataFormat = LinkedDataFormat.JSON

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._store = {}
        if self.file_path is not None:
            p = Path(self.file_path)
            if p.exists():
                with open(p) as f:
                    self._store = json.load(f)

    def _persist(self):
        """Write store to file if file_path is set."""
        if self.file_path is not None:
            with open(self.file_path, "w") as f:
                json.dump(self._store, f, indent=2)

    def resolve_iris(self, iris: List[str]) -> Dict[str, Dict]:
        jsonld_dicts = {}
        for iri in iris:
            jsonld_dicts[iri] = self._store.get(iri, None)
        return jsonld_dicts

    def store_json_dicts(self, json_dicts: Dict[str, Dict]) -> StoreResult:
        for iri, json_dict in json_dicts.items():
            self._store[iri] = json_dict
        self._persist()
        return StoreResult(success=True)

    def _filter(
        self,
        key: str,
        operator: str,
        value: Any,
        context: Optional[Dict[str, Dict]] = None,
        data: Optional[Dict[str, Dict]] = None,
    ) -> Set[str]:
        if data is None:
            data = self._store
        # retrieve property mapping from context
        # ToDo: use a jsonld expand here
        # if context is not None and key in context:
        #    key = context[key]
        matched_entities = set()
        for iri, jsonld_dict in data.items():
            if key in jsonld_dict:
                if apply_operator(operator, jsonld_dict[key], value):
                    matched_entities.add(iri)
        return matched_entities

    def _query(
        self,
        query: Union[Query, Condition],
        context: Dict = None,
        data: Optional[Dict[str, Dict]] = None,
    ) -> Set[str]:
        print("QUERY", query)
        if data is None:
            data = self._store
        if isinstance(query, Condition):
            return self._filter(query.field, query.operator, query.value, context, data)
        elif isinstance(query, Query):
            c1_res = self._query(query.op1, context, data)
            c2_res = self._query(query.op2, context, data)
            if query.operator == "and":
                # intersect the results
                return c1_res & c2_res
            elif query.operator == "or":
                # union the results
                return c1_res | c2_res
            else:
                raise NotImplementedError(f"Operator {query.operator} not implemented")
        else:
            raise ValueError("Invalid query type")

    def query(self, param: QueryParam) -> ResolveResult:
        context = None
        # if param.model_cls is not None:
        #     context = _get_schema(param.model_cls).get("@context", None)
        # elif self.model_cls is not None:
        #     context = _get_schema(self.model_cls).get("@context", None)
        iris = self._query(param.query, context)
        return self.resolve(ResolveParam(iris=list(iris), model_cls=param.model_cls))


class SqliteDocumentStore(Backend):
    db_path: Union[Path, str]
    format: LinkedDataFormat = LinkedDataFormat.JSON
    persist_connection: bool = False
    _conn: Optional[sqlite3.Connection] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if self.db_path == ":memory:":
            self.persist_connection = True
            self._conn = sqlite3.connect(self.db_path)

        # create table 'entities' if not exists
        conn = self._conn if self.persist_connection else sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                data JSONB
            )
            """
        )
        conn.commit()
        if not self.persist_connection:
            conn.close()

    def close(self):
        """Close the persistent connection if it exists."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def resolve_iris(self, iris: List[str]) -> Dict[str, Dict]:
        jsonld_dicts = {}
        conn = self._conn if self.persist_connection else sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """
            SELECT id, data FROM entities WHERE id IN ({})
            """.format(
                ",".join("?" for _ in iris)
            ),
            iris,
        )
        rows = c.fetchall()
        for iri, data in rows:
            jsonld_dicts[iri] = json.loads(data)
        if not self.persist_connection:
            conn.close()
        return jsonld_dicts

    def _store_dicts(self, dicts: Dict[str, Dict]) -> StoreResult:
        conn = self._conn if self.persist_connection else sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.executemany(
            """
            INSERT OR REPLACE INTO entities (id, data) VALUES (?, ?)
            """,
            [(iri, json.dumps(d)) for iri, d in dicts.items()],
        )
        conn.commit()
        if not self.persist_connection:
            conn.close()
        return StoreResult(success=True)

    def store_json_dicts(self, json_dicts: Dict[str, Dict]) -> StoreResult:
        return self._store_dicts(json_dicts)

    def query():
        raise NotImplementedError()
