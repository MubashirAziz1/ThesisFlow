import logging

from langchain.chat_models import BaseChatModel
from ..config.app_config import AppConfig
from ..reflection.resolver import resolve_class


logger = logging.getLogger(__name__)


def create_chat_model(name: str | None = None, thinking_enabled: bool = False, *, app_config: AppConfig | None = None, **kwargs) -> BaseChatModel:
    """ Create a chat model instance from the config. """

    config = app_config
    if name is None:
        if not config.models:
            raise ValueError("No models defined in config")
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
        },
    )

    reasoning = getattr(model_config, "reasoning", None)
    if isinstance(reasoning, (bool, str)):
        model_settings_from_config["reasoning"] = reasoning

    if thinking_enabled:
        if not model_config.supports_thinking:
            raise ValueError(
                f"Model {name} does not support thinking. "
                "Set `supports_thinking: true` in config.yaml to enable it."
            )
        if model_config.when_thinking_enabled:
            model_settings_from_config.update(model_config.when_thinking_enabled)
    else:
        if model_config.when_thinking_disabled:
            model_settings_from_config.update(model_config.when_thinking_disabled)


    effective_model_settings = dict(model_settings_from_config)
    effective_model_settings.update({key: value for key, value in kwargs.items() if value is not None})
    model_instance = model_class(**effective_model_settings)

    return model_instance