import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .dataBase import Database
from .graph import build_query_graph
from .logger import logger
from .mcp_sql import HttpMcpSqlConverter


class QueryRequest(BaseModel):
    query: str


app = FastAPI(
    title="ATLAS",
    description="SQL-backed query service for natural-language database queries.",
    version="1.0.0",
)


def create_query_graph():
    database = Database(os.getenv("DATABASE_URL"))
    converter = HttpMcpSqlConverter(os.getenv("MCP_SQL_CONVERTER_URL"))
    return build_query_graph(converter, database)


query_graph = create_query_graph()


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
@app.post("/")
def query_endpoint(request: QueryRequest | None = None) -> dict[str, Any]:
    query = (request.query if request else "").strip() if isinstance(request, QueryRequest) else ""
    if not query:
        payload = {}
        if hasattr(request, "query"):
            payload = request.model_dump() if hasattr(request, "model_dump") else request.dict()
        if payload.get("query"):
            query = str(payload["query"]).strip()

    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        result = query_graph.invoke({"query": query})
        response = result.get("response")
        if response:
            return {"response": response}
        if result.get("error"):
            logger.error("Query failed: %s", result["error"])
            raise HTTPException(status_code=500, detail=result["error"])
        return {"response": "I couldn't find any matching data."}
    except Exception as exc:  # pragma: no cover - surfaced to API clients
        logger.exception("Unhandled query error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
