"""PostgreSQL startup helpers and optional real-database persistence check."""

import asyncio
import os
from urllib.parse import parse_qs, quote, urlsplit
from uuid import uuid4

import pytest
from fastapi import FastAPI
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import create_async_engine

from app.gateway.deps import langgraph_runtime
from packages.harness.thesisflow.config.app_config import AppConfig
from packages.harness.thesisflow.persistence import engine as engine_module
from packages.harness.thesisflow.persistence.postgres_schema import (
    create_schema_sql,
    dsn_with_search_path,
)


def test_schema_sql_uses_current_package_and_rejects_invalid_identifiers():
    assert create_schema_sql("deerflow") == 'CREATE SCHEMA IF NOT EXISTS "deerflow"'
    assert create_schema_sql("") is None
    with pytest.raises(ValueError):
        create_schema_sql('unsafe"; DROP SCHEMA public; --')


@pytest.mark.parametrize("keyword_dsn", [False, True])
def test_search_path_preserves_other_libpq_options(keyword_dsn):
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    options = r"-c application_name=research\ assistant -csearch_path=old -c statement_timeout=5000"
    dsn = (
        make_conninfo(host="localhost", dbname="test", options=options)
        if keyword_dsn
        else f"postgresql+asyncpg://localhost/test?sslmode=require&options={quote(options, safe='')}"
    )
    result = dsn_with_search_path(dsn, "deerflow")
    params = conninfo_to_dict(result)
    assert params["options"] == r"-c application_name=research\ assistant -c statement_timeout=5000 -c search_path=deerflow"
    if not keyword_dsn:
        assert urlsplit(result).scheme == "postgresql"
        assert parse_qs(urlsplit(result).query)["sslmode"] == ["require"]


def test_search_path_added_to_plain_url():
    result = dsn_with_search_path("postgresql://localhost/test", "deerflow")
    assert parse_qs(urlsplit(result).query)["options"] == ["-c search_path=deerflow"]


def test_postgres_engine_initialization_uses_current_package(monkeypatch):
    """Exercise PostgreSQL setup without opening a network connection."""
    calls = []

    def make_engine(url, **kwargs):
        calls.append((url, kwargs))
        return create_async_engine(url, **kwargs)

    monkeypatch.setattr(engine_module, "create_async_engine", make_engine)

    async def scenario():
        try:
            await engine_module.init_engine("postgres", url="postgresql+asyncpg://localhost/test")
            assert engine_module.get_session_factory() is not None
            assert calls[0][1]["connect_args"]["command_timeout"] == 30
        finally:
            await engine_module.close_engine()

    asyncio.run(scenario())


@pytest.mark.skipif(os.getenv("THESISFLOW_TEST_POSTGRES") != "1", reason="requires configured PostgreSQL")
def test_checkpoint_survives_application_restart():
    config = AppConfig.from_file()
    assert config.database.backend == "postgres"
    thread_id = f"persistence-smoke-{uuid4()}"
    run_config = {"configurable": {"thread_id": thread_id}}
    builder = StateGraph(dict)
    builder.add_node("echo", lambda state: state)
    builder.add_edge(START, "echo")
    builder.add_edge("echo", END)
    expected = {"message": "PostgreSQL checkpoint survives restart"}

    async def scenario():
        try:
            async with langgraph_runtime(app, config):
                graph = builder.compile(checkpointer=app.state.checkpointer)
                assert await graph.ainvoke(expected, run_config) == expected

            async with langgraph_runtime(app, config):
                graph = builder.compile(checkpointer=app.state.checkpointer)
                snapshot = await graph.aget_state(run_config)
                assert snapshot.values == expected
        finally:
            async with langgraph_runtime(app, config):
                await app.state.checkpointer.adelete_thread(thread_id)

    app = FastAPI()
    asyncio.run(scenario(), loop_factory=asyncio.SelectorEventLoop)
