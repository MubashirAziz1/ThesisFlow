import logging

from langchain.chat_models import BaseChatModel
from langchain_openai.chat_models.base import BaseChatOpenAI

from ..config.app_config import AppConfig, get_app_config
from ..reflection.resolver import resolve_class




def create_chat_model(name: str | None = None, thinking_enabled: bool = False, *, app_config: AppConfig | None = None, **kwargs) -> BaseChatModel:
    """ Create a chat model instance from the config. """

    config = app_config or get_app_config()
    if name is None:
        name = config.models[0].name
    model_config = config.get_model_config(name)
    if model_config is None:
        raise ValueError(f"Model {name} not found in config") from None
    model_class = resolve_class(model_config.use, BaseChatModel)
    model_settings_from_config = model_config.model_dump(
        exclude_none=True,
        exclude={
            "use",
            "name",
            "display_name",
            "description",
            "supports_thinking",
            "supports_reasoning_effort",
            "when_thinking_enabled",
            "when_thinking_disabled",
            "thinking",
            "supports_vision",
            # Runtime/UI metadata used to size the context indicator. Provider
            # clients do not accept this as a model-constructor argument.
            "context_window",
            # Presentation-only metadata (consumed by the console's cost
            # display) — must never reach the provider client, which would
            # forward unknown kwargs into the completion request payload.
            "pricing",
            "request_admission",
        },
    )

    effective_model_settings = dict(model_settings_from_config)
    effective_model_settings.update({key: value for key, value in kwargs.items() if value is not None})
    model_instance = model_class(**effective_model_settings)
    
    return model_instance