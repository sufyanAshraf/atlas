import json
import os
from collections import defaultdict
from contextlib import closing
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

DEFAULT_DATABASE_URL = "postgresql://agent_ro:agent_ro_pw@localhost:5432/mydb"


class Database:
    """Small read-only PostgreSQL adapter used by the query graph."""

    def __init__(self,url: str | None = None, schema_name: str = "public", statement_timeout_ms: int = 10_000, max_rows: int = 500):
        self.url = url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
        self.schema_name = schema_name
        self.statement_timeout_ms = statement_timeout_ms
        self.max_rows = max_rows

    def _connect(self):
        connection = psycopg2.connect(
            self.url,
            options=f"-c statement_timeout={self.statement_timeout_ms}",
        )
        # Postgres itself rejects INSERT/UPDATE/DELETE/DDL in a read-only transaction,
        # including data-modifying CTEs hidden inside a WITH query.
        connection.set_session(readonly=True, autocommit=False)
        return connection

    def schema(self) -> str:
        query = """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position
        """
        try:
            with closing(self._connect()) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, (self.schema_name,))
                    columns = cursor.fetchall()
        except psycopg2.OperationalError:
            return "No database schema is available."

        tables: dict[str, list[str]] = defaultdict(list)
        for table, column, data_type in columns:
            tables[table].append(f"{column} {data_type}")
        if not tables:
            return "No database schema is available."
        return "\n".join(f"{table}({', '.join(cols)})" for table, cols in tables.items())

    def execute_readonly(self, sql: str) -> list[dict[str, Any]]:
        statement = sql.strip().rstrip(";").strip()
        if not statement or not statement.lower().startswith(("select", "with")):
            raise ValueError("Only read-only SELECT and WITH queries are allowed.")
        if ";" in statement:
            raise ValueError("Multiple SQL statements are not allowed.")

        with closing(self._connect()) as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(statement)
                rows = cursor.fetchmany(self.max_rows)
            connection.rollback()
        return [dict(row) for row in rows]
 
def serialise_rows(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, default=str)  # handles Decimal and date values from Postgres