from pydantic import BaseModel, ConfigDict, Field


class LeadAgentConfig(BaseModel):
    """Config section for the lead agent (the `lead-agent:` block in config.yaml)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    model_name: str | None = Field(default=None, description="Default model name for the lead agent")
    is_plan_mode: bool = Field(default=False, description="Enable plan mode (TodoList) by default")
    thinking_enabled: bool = Field(default=False, description="Enable thinking mode by default")
    reasoning_effort: str = Field(default="low", description="Reasoning effort by default")
