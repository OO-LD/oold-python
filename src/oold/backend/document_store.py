import json
import sqlite3
from pathlib import Path
from typing import Any

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

    _store: dict[str, dict] | None = None
    file_path: Path | str | None = None
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

    def resolve_iris(self, iris: list[str]) -> dict[str, dict]:
        jsonld_dicts = {}
        for iri in iris:
            jsonld_dicts[iri] = self._store.get(iri, None)
        return jsonld_dicts

    def store_json_dicts(self, json_dicts: dict[str, dict]) -> StoreResult:
        for iri, json_dict in json_dicts.items():
            self._store[iri] = json_dict
        self._persist()
        return StoreResult(success=True)

    def _filter(
        self,
        key: str,
        operator: str,
        value: Any,
        context: dict[str, dict] | None = None,
        data: dict[str, dict] | None = None,
    ) -> set[str]:
        if data is None:
            data = self._store
        # retrieve property mapping from context
        # ToDo: use a jsonld expand here
        # if context is not None and key in context:
        #    key = context[key]
        matched_entities = set()
        for iri, jsonld_dict in data.items():
            if key in jsonld_dict and apply_operator(operator, jsonld_dict[key], value):
                matched_entities.add(iri)
        return matched_entities

    def _query(
        self,
        query: Query | Condition,
        context: dict | None = None,
        data: dict[str, dict] | None = None,
    ) -> set[str]:
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
            raise TypeError("Invalid query type")

    def query(self, param: QueryParam) -> ResolveResult:
        context = None
        # if param.model_cls is not None:
        #     context = _get_schema(param.model_cls).get("@context", None)
        # elif self.model_cls is not None:
        #     context = _get_schema(self.model_cls).get("@context", None)
        iris = self._query(param.query, context)
        return self.resolve(ResolveParam(iris=list(iris), model_cls=param.model_cls))


class SqliteDocumentStore(Backend):
    db_path: Path | str
    format: LinkedDataFormat = LinkedDataFormat.JSON
    persist_connection: bool = False
    _conn: sqlite3.Connection | None = None

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

    def resolve_iris(self, iris: list[str]) -> dict[str, dict]:
        jsonld_dicts = {}
        conn = self._conn if self.persist_connection else sqlite3.connect(self.db_path)
        c = conn.cursor()
        # Only the number of `?` placeholders is interpolated; the actual IRI
        # values are bound as query parameters, so this is not an injection vector.
        placeholders = ",".join("?" for _ in iris)
        c.execute(
            f"SELECT id, data FROM entities WHERE id IN ({placeholders})",  # noqa: S608
            iris,
        )
        rows = c.fetchall()
        for iri, data in rows:
            jsonld_dicts[iri] = json.loads(data)
        if not self.persist_connection:
            conn.close()
        return jsonld_dicts

    def _store_dicts(self, dicts: dict[str, dict]) -> StoreResult:
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

    def store_json_dicts(self, json_dicts: dict[str, dict]) -> StoreResult:
        return self._store_dicts(json_dicts)

    def query():
        raise NotImplementedError()
