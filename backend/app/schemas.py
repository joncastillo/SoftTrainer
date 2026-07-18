"""Pydantic models shared by the REST and WebSocket APIs."""

from typing import Optional
from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    """Request body for starting a new training session."""

    scenario: str = Field(min_length=3, description="What the user wants to practise")
    provider_id: Optional[str] = None
    duration_minutes: int = Field(default=15, ge=2, le=120)
    subtitles: bool = True
    document_ids: list[str] = Field(default_factory=list)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    key_points: list[str] = Field(
        default_factory=list, max_length=5,
        description="Points the user wants to land during the session")
    pressure: str = Field(
        default="off", pattern="^(off|low|medium|high)$",
        description="Heckler/distraction intensity during the session")
    grounding: bool = Field(
        default=False, description="Start with a short breathing exercise")


class ProviderConfig(BaseModel):
    """A configured LLM provider entry."""

    id: str
    kind: str = Field(pattern="^(openai-compatible|anthropic|ollama|local-hf)$")
    label: str
    base_url: Optional[str] = None
    model: str
    api_key: Optional[str] = None
    api_key_env: Optional[str] = None
    active: bool = False


class DownloadRequest(BaseModel):
    repo_id: str


class LoadRequest(BaseModel):
    repo_id: str
