"""OpenAI Responses API request schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class InputTextItem(BaseModel):
    """OpenAI input text content item."""

    type: Literal["input_text"] = "input_text"
    text: str


class InputMessageItem(BaseModel):
    """OpenAI Responses input message item."""

    type: Literal["message"] = "message"
    role: Literal["user", "system", "developer", "assistant"]
    content: List[InputTextItem]


class FunctionCallItem(BaseModel):
    """OpenAI Responses function call input item."""

    type: Literal["function_call"] = "function_call"
    call_id: str
    name: str
    arguments: str


class FunctionCallOutputItem(BaseModel):
    """OpenAI Responses function call output input item."""

    type: Literal["function_call_output"] = "function_call_output"
    call_id: str
    output: str


class FunctionTool(BaseModel):
    """OpenAI Responses function tool definition."""

    type: Literal["function"] = "function"
    name: str
    description: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    strict: bool = False


class WebSearchToolFilters(BaseModel):
    """OpenAI web search tool filters."""

    allowed_domains: Optional[List[str]] = None


class WebSearchToolUserLocation(BaseModel):
    """OpenAI web search user location."""

    type: Literal["approximate"] = "approximate"
    country: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    timezone: Optional[str] = None


class WebSearchTool(BaseModel):
    """OpenAI Responses web search tool definition."""

    type: Literal["web_search"] = "web_search"
    filters: Optional[WebSearchToolFilters] = None
    user_location: Optional[WebSearchToolUserLocation] = None
    external_web_access: Optional[bool] = None


class ToolChoiceFunction(BaseModel):
    """Tool choice specifying a function."""

    type: Literal["function"] = "function"
    name: str


class ToolChoiceWebSearch(BaseModel):
    """Tool choice specifying web search."""

    type: Literal["web_search"] = "web_search"


ToolChoice = Union[Literal["auto", "none"], ToolChoiceFunction, ToolChoiceWebSearch]

InputItem = Union[InputMessageItem, FunctionCallItem, FunctionCallOutputItem]

ResponseTool = Union[FunctionTool, WebSearchTool]


class OpenAIResponsesRequest(BaseModel):
    """OpenAI Responses API request model."""

    model: str
    input: List[InputItem]
    instructions: Optional[str] = None
    tools: Optional[List[ResponseTool]] = None
    tool_choice: Optional[ToolChoice] = None
    max_output_tokens: Optional[int] = None
    max_tool_calls: Optional[int] = None
    include: Optional[List[str]] = None
