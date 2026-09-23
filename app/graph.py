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

    def execute(state: QueryState) -> QueryState:
        try:
            return {"rows": database.execute_readonly(state["sql"]), "error": ""}
        except Exception as exc:
            return {"error": str(exc)}

    def respond(state: QueryState) -> QueryState:
        rows = state.get("rows", [])
        if not rows:
            return {"response": "I couldn't find any matching data."}
        return {"response": serialise_rows(rows)}

    def route_after_execute(state: QueryState) -> str:
        if not state.get("error"):
            return "respond"
        if state.get("attempts", 0) >= MAX_ATTEMPTS:
            raise QueryFailedError(
                f"SQL query failed after {MAX_ATTEMPTS} attempts: {state['error']}"
            )
        return "convert"

    def route_after_convert(state: QueryState) -> str:
        if not state.get("error"):
            return "execute"
        if state.get("attempts", 0) >= MAX_ATTEMPTS:
            raise QueryFailedError(
                f"SQL query failed after {MAX_ATTEMPTS} attempts: {state['error']}"
            )
        return "convert"

