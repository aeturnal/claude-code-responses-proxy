"""Anthropic Messages API request schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    """Anthropic text content block."""

    type: Literal["text"] = "text"
    text: str
    citations: Optional[List[Dict[str, Any]]] = None


class ToolReferenceBlock(BaseModel):
    """Tool reference content within a tool result."""

    type: Literal["tool_reference"] = "tool_reference"
    tool_name: str


ToolResultContentBlock = Union[TextBlock, ToolReferenceBlock, Dict[str, Any]]


class ToolResultBlock(BaseModel):
    """Anthropic tool result content block."""

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: Union[str, List[ToolResultContentBlock], Dict[str, Any]]


class ToolUseBlock(BaseModel):
    """Anthropic tool use content block."""

    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: Dict[str, Any]
    cache_control: Optional[Dict[str, Any]] = None


class ServerToolUseBlock(BaseModel):
    """Anthropic server tool use content block."""

    type: Literal["server_tool_use"] = "server_tool_use"
    id: str
    name: str
    input: Dict[str, Any]


class WebSearchResult(BaseModel):
    """Anthropic web search result item."""

    type: Literal["web_search_result"] = "web_search_result"
    url: str
    title: Optional[str] = None
    encrypted_content: Optional[str] = None
    page_age: Optional[str] = None


class WebSearchToolResultBlock(BaseModel):
    """Anthropic web search tool result content block."""

    type: Literal["web_search_tool_result"] = "web_search_tool_result"
    tool_use_id: str
    content: Union[List[WebSearchResult], Dict[str, Any]]


ContentBlock = Union[
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    ServerToolUseBlock,
    WebSearchToolResultBlock,
]


class Message(BaseModel):
    """Anthropic message entry."""

    role: Literal["user", "assistant"]
    content: Union[str, List[ContentBlock]]


class ToolDefinition(BaseModel):
    """Anthropic tool definition."""

    type: Optional[str] = None
    name: str
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    strict: Optional[bool] = None
    max_uses: Optional[int] = None
    allowed_domains: Optional[List[str]] = None
    blocked_domains: Optional[List[str]] = None
    user_location: Optional[Dict[str, Any]] = None


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
    stream: Optional[bool] = None


class CountTokensResponse(BaseModel):
    """Anthropic /v1/messages/count_tokens response model."""

    input_tokens: int
