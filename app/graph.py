from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .dataBase import Database, serialise_rows
from .mcp_sql import SqlConverter

MAX_ATTEMPTS = 3


class QueryFailedError(RuntimeError):
    pass


class QueryState(TypedDict, total=False):
    query: str
    schema: str
    sql: str
    rows: list[dict[str, Any]]
    error: str
    attempts: int
    response: str


def build_query_graph(converter: SqlConverter, database: Database):
    def convert(state: QueryState) -> QueryState:
        attempts = state.get("attempts", 0) + 1
        try:
            sql = converter.convert(
                state["query"],
                state.get("schema", database.schema()),
                state.get("sql"),
                state.get("error"),
            )
            return {"sql": sql, "attempts": attempts, "error": ""}
        except Exception as exc:
            return {"attempts": attempts, "error": f"SQL conversion failed: {exc}"}

    