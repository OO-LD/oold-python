try:
    import psycopg
    from psycopg import sql
    from psycopg.types.json import Jsonb
except ImportError as exc:
    raise ImportError("PostgresDocumentStore needs psycopg, install it with: pip install 'oold[postgres]'") from exc

from pydantic import Field

from oold.backend.interface import Backend, LinkedDataFormat, StoreResult


class PostgresDocumentStore(Backend):
    """Persist entities as JSONB rows in PostgreSQL, one row per IRI."""

    dsn: str
    table: str = Field(default="entities", pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
    format: LinkedDataFormat = LinkedDataFormat.JSON
    _conn: psycopg.Connection | None = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self._connection().cursor() as cur:
            cur.execute(
                sql.SQL("CREATE TABLE IF NOT EXISTS {} (id TEXT PRIMARY KEY, data JSONB)").format(
                    sql.Identifier(self.table)
                )
            )

    def _connection(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self.dsn, autocommit=True)
        return self._conn

    def close(self):
        """Close the connection if it is open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def resolve_iris(self, iris: list[str]) -> dict[str, dict]:
        query = sql.SQL("SELECT id, data FROM {} WHERE id = ANY(%s::text[])").format(sql.Identifier(self.table))
        with self._connection().cursor() as cur:
            cur.execute(query, (iris,))
            return dict(cur.fetchall())

    def store_json_dicts(self, json_dicts: dict[str, dict]) -> StoreResult:
        query = sql.SQL(
            "INSERT INTO {} (id, data) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data"
        ).format(sql.Identifier(self.table))
        conn = self._connection()
        with conn.transaction(), conn.cursor() as cur:
            cur.executemany(query, [(iri, Jsonb(d)) for iri, d in json_dicts.items()])
        return StoreResult(success=True)
