"""Lifespan wiring for the LangGraph runtime singletons."""

import asyncio
from unittest.mock import AsyncMock

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.gateway.app import create_app
from app.gateway.deps import get_run_manager, langgraph_runtime
from packages.harness.thesisflow.config import app_config as app_config_module
from packages.harness.thesisflow.config.app_config import AppConfig
from packages.harness.thesisflow.runtime.runs.manager import RunManager
from packages.harness.thesisflow.runtime.runs.schemas import RunStatus


def test_langgraph_runtime_exposes_singletons_and_drains_on_exit():
    """The context keeps the run manager alive, then interrupts inflight work."""

    async def scenario() -> None:
        app = FastAPI()
        config = AppConfig()
        started = asyncio.Event()

        async with langgraph_runtime(app, config):
            assert app.state.app_config is config
            manager = app.state.run_manager
            assert isinstance(manager, RunManager)
            assert manager.heartbeat_enabled is False

            record = await manager.create_or_reject("thread-1")
            record.status = RunStatus.running

            async def hang() -> None:
                started.set()
                await asyncio.Event().wait()

            record.task = asyncio.create_task(hang())
            await started.wait()

        assert record.status is RunStatus.interrupted
        assert record.task is not None
        assert record.task.done()
        assert app.state.run_manager is None
        assert app.state.app_config is None

    asyncio.run(scenario())


def test_lifespan_serves_requests_before_runtime_shutdown(monkeypatch):
    """Gateway startup must yield while the runtime is still installed."""
    events: list[str] = []
    original_shutdown = RunManager.shutdown

    async def spy(self: RunManager, *, timeout: float = 5.0) -> None:
        events.append("shutdown")
        await original_shutdown(self, timeout=timeout)

    monkeypatch.setattr(RunManager, "shutdown", spy)
    monkeypatch.setattr("app.gateway.app.get_app_config", lambda: AppConfig())

    app = create_app()

    @app.get("/runtime-check")
    def runtime_check(request: Request):
        manager = get_run_manager(request)
        return {
            "has_manager": manager is request.app.state.run_manager,
            "has_config": request.app.state.app_config is not None,
        }

    with TestClient(app) as client:
        events.append("serving")
        health = client.get("/health")
        runtime = client.get("/runtime-check")
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"
        assert runtime.status_code == 200
        assert runtime.json() == {"has_manager": True, "has_config": True}

    assert events == ["serving", "shutdown"]


def test_get_app_config_returns_the_loaded_snapshot(tmp_path, monkeypatch):
    """Startup must hand the runtime the config it just loaded, not None."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("log_level: warning\n", encoding="utf-8")
    monkeypatch.setattr(app_config_module, "_app_config", None)
    monkeypatch.setattr(
        AppConfig,
        "resolve_config_path",
        classmethod(lambda cls: config_path),
    )

    loaded = app_config_module.get_app_config()
    again = app_config_module.get_app_config()

    assert isinstance(loaded, AppConfig)
    assert loaded.log_level == "warning"
    assert again is loaded


def test_create_run_uses_the_lifespan_run_manager(monkeypatch):
    """POST /runs must admit a run on the manager installed by lifespan."""
    app_config = AppConfig()
    monkeypatch.setattr("app.gateway.app.get_app_config", lambda: app_config)
    monkeypatch.setattr("app.gateway.services.get_app_config", lambda: app_config)
    monkeypatch.setattr("app.gateway.services.resolve_agent_factory", lambda _assistant_id: lambda **_kwargs: None)
    monkeypatch.setattr("app.gateway.services.run_agent", AsyncMock())

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/threads/thread-1/runs",
            json={
                "assistant_id": "lead_agent",
                "input": {"messages": [{"role": "user", "content": "hello"}]},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["thread_id"] == "thread-1"
    assert body["assistant_id"] == "lead_agent"
    assert body["status"] == "pending"
    assert body["run_id"]
