import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Union

from oold.backend.interface import Backend, StoreResult


class SimpleDictDocumentStore(Backend):
    _store: Optional[Dict[str, dict]] = None

    def __init__(self):
        self._store = {}

    def resolve_iris(self, iris: List[str]) -> Dict[str, Dict]:
        jsonld_dicts = {}
        for iri in iris:
            jsonld_dicts[iri] = self._store.get(iri, None)
        return jsonld_dicts

    def store_jsonld_dicts(self, jsonld_dicts: Dict[str, Dict]) -> StoreResult:
        for iri, jsonld_dict in jsonld_dicts.items():
            self._store[iri] = jsonld_dict
        return StoreResult(success=True)

    def query():
        pass


class SqliteDocumentStore(Backend):
    db_path: Union[Path, str]
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

    def store_jsonld_dicts(self, jsonld_dicts: Dict[str, Dict]) -> StoreResult:
        conn = self._conn if self.persist_connection else sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.executemany(
            """
            INSERT OR REPLACE INTO entities (id, data) VALUES (?, ?)
            """,
            [
                (iri, json.dumps(jsonld_dict))
                for iri, jsonld_dict in jsonld_dicts.items()
            ],
        )
        conn.commit()
        if not self.persist_connection:
            conn.close()
        return StoreResult(success=True)

    def query():
        raise NotImplementedError()
