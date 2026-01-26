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
    role: Literal["user", "system", "developer"]
    content: List[InputTextItem]


class FunctionDefinition(BaseModel):
    """OpenAI function tool definition."""

    name: str
    description: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)


class FunctionTool(BaseModel):
    """OpenAI Responses function tool wrapper."""

    type: Literal["function"] = "function"
    function: FunctionDefinition
    strict: bool = False


class ToolChoiceFunctionDetail(BaseModel):
    """Tool choice detail for a specific function."""

    name: str


class ToolChoiceFunction(BaseModel):
    """Tool choice specifying a function."""

    type: Literal["function"] = "function"
    function: ToolChoiceFunctionDetail


ToolChoice = Union[Literal["auto", "none"], ToolChoiceFunction]


class OpenAIResponsesRequest(BaseModel):
    """OpenAI Responses API request model."""

    model: str
    input: List[InputMessageItem]
    instructions: Optional[str] = None
    tools: Optional[List[FunctionTool]] = None
    tool_choice: Optional[ToolChoice] = None
    max_output_tokens: Optional[int] = None
