from pydantic import BaseModel, ConfigDict, Field
    
class ModelConfig(BaseModel):
    """Config section for a model"""

    name: str = Field(..., description="Unique name for the model")
    use: str = Field(
        ...,
        description="Class path of the model provider(e.g. langchain_openai.ChatOpenAI)",
    )
    model: str = Field(..., description="Model name")
    display_name: str | None = Field(..., default_factory=lambda: None, description="Display name for the model")
    description: str | None = Field(..., default_factory=lambda: None, description="Description for the model")
    model_config = ConfigDict(extra="allow")

    use_responses_api: bool | None = Field(
        default=None,
        description="Whether to route OpenAI ChatOpenAI calls through the /v1/responses API",
    )
   
    supports_thinking: bool = Field(default_factory=lambda: False, description="Whether the model supports thinking")
    supports_reasoning_effort: bool = Field(default_factory=lambda: False, description="Whether the model supports reasoning effort")
    when_thinking_enabled: dict | None = Field(
        default_factory=lambda: None,
        description="Extra settings to be passed to the model when thinking is enabled",
    )
    when_thinking_disabled: dict | None = Field(
        default_factory=lambda: None,
        description="Extra settings to be passed to the model when thinking is disabled",
    )
    supports_vision: bool = Field(default_factory=lambda: False, description="Whether the model supports vision/image inputs")
    context_window: int | None = Field(
        default=None,
        gt=0,
        description=(
            "Positive total context window size in tokens (prompt + completion). Used to compute the real-time "
            "context usage percentage displayed in the chat UI, and attached to the model's langchain profile "
            "(`max_input_tokens`) so fraction-based summarization triggers can resolve their thresholds for "
            "third-party OpenAI-compatible models that carry no built-in profile. Distinct from `max_tokens`, "
            "which is the per-call output cap passed to the provider. Leave unset if unknown; the UI will hide "
            "the percentage and fraction summarization clauses will degrade with a warning."
        ),
    )

