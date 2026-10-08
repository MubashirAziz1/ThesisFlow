"""One check that the run service admits a single thread run."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.gateway.run_models import RunCreateRequest
from app.gateway.services import start_run
from packages.harness.thesisflow.runtime.runs.manager import RunManager
from packages.harness.thesisflow.runtime.runs.schemas import RunStatus


def test_start_run_admits_one_thread_run(monkeypatch):
    """start_run should create a pending run for the requested thread."""
    app_config = SimpleNamespace(
        lead_agent=SimpleNamespace(model_name=None, is_plan_mode=False),
        get_model_config=lambda _name: None,
    )
    monkeypatch.setattr("app.gateway.services.get_app_config", lambda: app_config)
    monkeypatch.setattr("app.gateway.services.resolve_agent_factory", lambda _assistant_id: lambda **_kwargs: None)
    monkeypatch.setattr("app.gateway.services.run_agent", AsyncMock())

    request = MagicMock()
    request.app.state.run_manager = RunManager()
    body = RunCreateRequest(
        assistant_id="lead_agent",
        input={"messages": [{"role": "user", "content": "hello"}]},
    )

    record = asyncio.run(start_run(body, "thread-1", request))

    assert record.thread_id == "thread-1"
    assert record.assistant_id == "lead_agent"
    assert record.status is RunStatus.pending
    assert record.run_id
