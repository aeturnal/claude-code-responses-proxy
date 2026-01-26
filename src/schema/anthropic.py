"""Anthropic Messages API request schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    """Anthropic text content block."""

    type: Literal["text"] = "text"
    text: str


class ToolResultBlock(BaseModel):
    """Anthropic tool result content block."""

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: Union[str, List[TextBlock]]


ContentBlock = Union[TextBlock, ToolResultBlock]


class Message(BaseModel):
    """Anthropic message entry."""

    role: Literal["user", "assistant"]
    content: Union[str, List[ContentBlock]]


class ToolDefinition(BaseModel):
    """Anthropic tool definition."""

    name: str
    description: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ToolChoiceSpecific(BaseModel):
    """Specific tool choice object."""

    type: Literal["tool"] = "tool"
    name: str


ToolChoice = Union[Literal["auto", "none"], ToolChoiceSpecific]


class MessagesRequest(BaseModel):
    """Anthropic /v1/messages request model."""

    model: str
    messages: List[Message]
    system: Optional[Union[str, List[TextBlock]]] = None
    tools: Optional[List[ToolDefinition]] = None
    tool_choice: Optional[ToolChoice] = None
    max_tokens: Optional[int] = None


class CountTokensResponse(BaseModel):
    """Anthropic /v1/messages/count_tokens response model."""

    input_tokens: int
