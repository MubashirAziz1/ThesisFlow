from pydantic import BaseModel, ConfigDict, Field

class ModelConfig(BaseModel):
    """Config section for a model"""

    name: str = Field(..., description="Unique name for the model")
    display_name: str | None = Field(..., default_factory=lambda: None, description="Display name for the model")
    description: str | None = Field(..., default_factory=lambda: None, description="Description for the model")
    use: str = Field(..., description="Class path of the model provider(e.g. langchain_openai.ChatOpenAI)")
    model: str = Field(..., description="Model name")
    model_config = ConfigDict(extra="allow")