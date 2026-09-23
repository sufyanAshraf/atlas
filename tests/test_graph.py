import sqlite3

import pytest

from app.dataBase import Database
from app.graph import build_query_graph


class FakeConverter:
    def __init__(self, sqls):
        self.sqls = iter(sqls)
        self.calls = []

    def convert(self, query, schema, previous_sql=None, error=None):
        self.calls.append((query, previous_sql, error))
        return next(self.sqls)


def test_rewrites_failed_sql_and_returns_rows(tmp_path):
    path = tmp_path / "test.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE users (name TEXT)")
        connection.execute("INSERT INTO users VALUES ('Ada')")

    converter = FakeConverter(["SELECT missing FROM users", "SELECT name FROM users"])
    result = build_query_graph(converter, Database(str(path))).invoke({"query": "list users"})

    assert result["rows"] == [{"name": "Ada"}]
    assert result["attempts"] == 2
    assert converter.calls[1][2]


def test_stops_after_three_failed_attempts(tmp_path):
    path = tmp_path / "test.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE users (name TEXT)")

    converter = FakeConverter(["SELECT missing FROM users"] * 4)
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        build_query_graph(converter, Database(str(path))).invoke({"query": "list users"})
    assert len(converter.calls) == 3
