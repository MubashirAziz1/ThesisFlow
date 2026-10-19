"""Chat model construction must not forward config metadata to the provider."""

from packages.harness.thesisflow.config.app_config import AppConfig
from packages.harness.thesisflow.models.factory import create_chat_model


class _RecordingModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_create_chat_model_omits_metadata_from_provider_kwargs(monkeypatch):
    """Provider constructors receive model settings, not capability flags."""
    monkeypatch.setattr(
        "packages.harness.thesisflow.models.factory.resolve_class",
        lambda _use, _base: _RecordingModel,
    )
    app_config = AppConfig.model_validate(
        {
            "models": [
                {
                    "name": "demo",
                    "use": "langchain_openai:ChatOpenAI",
                    "model": "demo-model",
                    "supports_thinking": True,
                    "supports_reasoning_effort": False,
                    "supports_vision": False,
                    "when_thinking_disabled": {"extra_body": {"thinking": {"type": "disabled"}}},
                }
            ]
        }
    )
    app_config._models_by_name = {model.name: model for model in app_config.models}

    created = create_chat_model("demo", thinking_enabled=False, app_config=app_config)

    assert created.kwargs["model"] == "demo-model"
    assert created.kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "supports_thinking" not in created.kwargs
    assert "supports_reasoning_effort" not in created.kwargs
    assert "supports_vision" not in created.kwargs
    assert "when_thinking_enabled" not in created.kwargs
    assert "when_thinking_disabled" not in created.kwargs
    assert "context_window" not in created.kwargs
