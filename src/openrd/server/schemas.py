from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProviderIn(BaseModel):
    name: str
    base_url: str = "https://polza.ai/api/v1"
    api_key: str | None = None
    roles: dict[str, str] = Field(
        default_factory=lambda: {
            "orchestrator": "openai/gpt-4.1",
            "researcher": "openai/gpt-4o-mini",
            "critic": "openai/gpt-4.1",
            "coder": "openai/gpt-4.1",
        }
    )


class ProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    roles: dict[str, str] | None = None


class ProjectIn(BaseModel):
    name: str
    goal: str
    prompt: str = ""
    description: str = ""
    kpi: dict[str, Any] = Field(default_factory=dict)
    provider_id: str | None = None
    think_slots: int = 4
    exec_slots: int = 1
    profile: str = "default"
    rigor: str = "high"
    user_ideas: str = ""


class ProjectPatch(BaseModel):
    name: str | None = None
    goal: str | None = None
    prompt: str | None = None
    kpi: dict[str, Any] | None = None


class SecretIn(BaseModel):
    name: str
    value: str
    note: str = ""


class AskIn(BaseModel):
    kind: str = "clarify"
    question: str
    secret_name: str | None = None
    blocked_job_ids: list[str] = Field(default_factory=list)


class AskReply(BaseModel):
    answer: str = ""
    secret_value: str | None = None
    decline: bool = False


class SteerIn(BaseModel):
    kind: str = "steer"
    content: str = ""
    node_id: str | None = None


class PluginToggle(BaseModel):
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
