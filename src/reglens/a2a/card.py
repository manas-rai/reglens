"""Agent Card — discovery document served at /.well-known/agent-card.json."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentSkill(BaseModel):
    id: str
    name: str
    description: str
    input_modes: list[str] = Field(default_factory=lambda: ["application/json"])
    output_modes: list[str] = Field(default_factory=lambda: ["application/json"])


class AgentCapabilities(BaseModel):
    streaming: bool = False
    push_notifications: bool = False
    state_transition_history: bool = False


class AgentCard(BaseModel):
    """A2A Agent Card — describes an agent's identity, capabilities, and skills."""

    name: str
    description: str
    url: str = Field(description="Base URL of the A2A server")
    version: str = "1.0.0"
    protocol_version: str = "0.2.5"
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    skills: list[AgentSkill] = Field(default_factory=list)
    default_input_mode: str = "application/json"
    default_output_mode: str = "application/json"
