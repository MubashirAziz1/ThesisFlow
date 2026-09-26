import logging
import os
from pathlib import Path
from typing import Any, Self

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from ..config.model_config import ModelConfig

load_dotenv()

logger = logging.getLogger(__name__)

class AppConfig(BaseModel):
    """Config for the DeerFlow application"""

    log_level: str = Field(
        default="info",
        description= "Logging level for app modules: debug, info, warning, or error."
    )
    models: list[ModelConfig] = Field(default_factory=list, description="Available models")

    @classmethod
    def from_file(cls, config_path: str | None = None) -> Self:
        """ Load config from YAML file. """
        
        resolved_path = cls.resolve_config_path(config_path)
        with open(resolved_path, encoding="utf-8") as f:
            return cls._from_yaml_text(f.read(), resolved_path)

    @classmethod
    def _from_yaml_text(cls, text: str, resolved_path: Path) -> Self:
        """ Build the config from already-read YAML *text* of *resolved_path*. """
        
        config_data = yaml.safe_load(text) or {}
        config_data = cls.resolve_env_variables(config_data)
        result = cls.model_validate(config_data)
        if not result.models:
            logger.warning(
                "No models are configured in %s. Add at least one entry under `models:` (see the commented examples in config.example.yaml) or run `make setup`.",
                resolved_path,
            )

        return result

    @classmethod
    def resolve_config_path(cls, config_path: str | None = None) -> Path:
        """ Resolve the config file path. """

        if config_path:
            path = Path(config_path)
            if not Path.exists(path):
                raise FileNotFoundError(f"Config file specified by param `config_path` not found at {path}")
            return path
        elif os.getenv("DEER_FLOW_CONFIG_PATH"):
            path = Path(os.getenv("DEER_FLOW_CONFIG_PATH"))
            if not Path.exists(path):
                raise FileNotFoundError(f"Config file specified by environment variable `DEER_FLOW_CONFIG_PATH` not found at {path}")
            return path
        else:
            raise FileNotFoundError("No such configuration file is present in the project.")
    
    @classmethod
    def resolve_env_variables(cls, config: Any) -> Any:
        """ Recursively resolve environment variables in the config. """
        if isinstance(config, str):
            if config.startswith("$"):
                env_value = os.getenv(config[1:])
                if env_value is None:
                    raise ValueError(f"Environment variable {config[1:]} not found for config value {config}")
                return env_value
            return config
        elif isinstance(config, dict):
            return {k: cls.resolve_env_variables(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [cls.resolve_env_variables(item) for item in config]
        return config


    def get_model_config(self, name: str) -> ModelConfig | None:
        """ Get the model config by name. """
       
        for model in self.models:
            if model.name == name:
                return model

        return None 

_app_config: AppConfig | None = None
_app_config_path: Path | None = None

def _load_and_cache_app_config(config_path: str | None = None) -> AppConfig:
    """ Load config from disk and refresh cache metadata. """
    global _app_config, _app_config_path

    resolved_path = AppConfig.resolve_config_path(config_path)
    raw = resolved_path.read_bytes()
    config = AppConfig._from_yaml_text(raw.decode("utf-8"), resolved_path)
    _app_config = config
    _app_config_path = resolved_path

    return _app_config

def get_app_config() -> AppConfig:
    """ Get the DeerFlow config instance. """

    global _app_config

    if _app_config is None:
        resolved_path = AppConfig.resolve_config_path()
        _load_and_cache_app_config(str(resolved_path))

    return _app_config

