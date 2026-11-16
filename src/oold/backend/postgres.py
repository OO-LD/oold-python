try:
    import psycopg
    from psycopg import sql
    from psycopg.types.json import Jsonb
except ImportError as exc:
    raise ImportError("PostgresDocumentStore needs psycopg, install it with: pip install 'oold[postgres]'") from exc

from typing import Any

from pydantic import Field

from oold.backend.interface import (
    Backend,
    ComparisonOperator,
    Condition,
    LinkedDataFormat,
    Query,
    QueryParam,
    ResolveResult,
    StoreResult,
    field_path,
)

# Fragments only: field names and values are always bound parameters.
_COMPARISONS = {
    ComparisonOperator.LT: "<",
    ComparisonOperator.LE: "<=",
    ComparisonOperator.GT: ">",
    ComparisonOperator.GE: ">=",
}


def _json_type(value: Any) -> str:
    return "string" if isinstance(value, str) else "null" if value is None else "number"


def _where(node: Query | Condition) -> tuple[str, list[Any]]:
    """Render a query tree as a WHERE clause and its parameters.

    Equality is jsonb containment, which a GIN index serves. Ranges compare the
    value at the path and only against values of the same JSON type: jsonb
    orders across types (null sorts below every number), Python raises.
    """
    if isinstance(node, Query):
        if node.operator not in ("and", "or"):
            raise NotImplementedError(f"Operator {node.operator} not implemented")
        left, left_params = _where(node.op1)
        right, right_params = _where(node.op2)
        return f"({left}) {node.operator.upper()} ({right})", left_params + right_params
    if not isinstance(node, Condition):
        raise TypeError("Invalid query type")

    path = field_path(node.field)
    operator = node.operator or ComparisonOperator.EQ
    if operator == ComparisonOperator.EQ:
        contained: Any = node.value
        for segment in reversed(path):
            contained = {segment: contained}
        return "data @> %s", [Jsonb(contained)]
    if operator == ComparisonOperator.NE:
        return "(data #> %s::text[]) <> %s", [path, Jsonb(node.value)]
    return (
        f"(jsonb_typeof(data #> %s::text[]) = %s AND (data #> %s::text[]) {_COMPARISONS[operator]} %s)",
        [path, _json_type(node.value), path, Jsonb(node.value)],
    )


class PostgresDocumentStore(Backend):
    """Persist entities as JSONB rows in PostgreSQL, one row per IRI.

    ``index`` adds a GIN index (``jsonb_path_ops``), which serves equality
    conditions on any path; range conditions scan the table.
    """

    dsn: str
    table: str = Field(default="entities", pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,57}$")
    format: LinkedDataFormat = LinkedDataFormat.JSON
    index: bool = True
    query_limit: int | None = Field(default=None, gt=0)
    _conn: psycopg.Connection | None = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        table = sql.Identifier(self.table)
        with self._connection().cursor() as cur:
            cur.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {} (id TEXT PRIMARY KEY, data JSONB)").format(table))
            if self.index:
                cur.execute(
                    sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} USING GIN (data jsonb_path_ops)").format(
                        sql.Identifier(f"{self.table}_gin"), table
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

    def _select(self, query: Query | Condition) -> tuple[sql.Composable, list[Any]]:
        where, params = _where(query)
        statement = sql.SQL("SELECT id, data FROM {} WHERE ").format(sql.Identifier(self.table)) + sql.SQL(where)
        statement += sql.SQL(" ORDER BY id")
        if self.query_limit is not None:
            statement += sql.SQL(" LIMIT %s")
            params.append(self.query_limit)
        return statement, params

    def query(self, param: QueryParam) -> ResolveResult:
        model_cls = self._model_cls_for(param.model_cls)
        statement, params = self._select(param.query)
        with self._connection().cursor() as cur:
            cur.execute(statement, params)
            return self._to_nodes(dict(cur.fetchall()), model_cls)
