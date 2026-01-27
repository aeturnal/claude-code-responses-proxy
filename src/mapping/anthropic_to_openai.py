"""Map Anthropic Messages requests to OpenAI Responses requests."""

from __future__ import annotations

import json
from typing import List, Optional, Union

from src.config import resolve_openai_model
from src.schema.anthropic import (
    Message,
    MessagesRequest,
    TextBlock,
    ToolChoiceSpecific,
    ToolResultBlock,
    ToolUseBlock,
)
from src.schema.openai import (
    FunctionTool,
    InputMessageItem,
    InputTextItem,
    OpenAIResponsesRequest,
    ToolChoice as OpenAIToolChoice,
    ToolChoiceFunction,
)


def _system_to_instructions(
    system: Optional[Union[str, List[TextBlock]]],
) -> Optional[str]:
    if system is None:
        return None
    if isinstance(system, str):
        return system
    instructions: List[str] = []
    for block in system:
        if not isinstance(block, TextBlock):
            raise ValueError(
                f"Unsupported system block type: {getattr(block, 'type', None)}"
            )
        instructions.append(block.text)
    return "\n".join(instructions)


def _tool_result_to_text(block: ToolResultBlock) -> str:
    if isinstance(block.content, str):
        return block.content
    texts: List[str] = []
    for item in block.content:
        if not isinstance(item, TextBlock):
            raise ValueError(
                f"Unsupported tool_result content block type: {getattr(item, 'type', None)}"
            )
        texts.append(item.text)
    return "\n".join(texts)


def _tool_use_to_text(block: ToolUseBlock) -> str:
    try:
        rendered_input = json.dumps(block.input, ensure_ascii=False, sort_keys=True)
    except TypeError:
        rendered_input = str(block.input)
    return f"[tool_use:{block.name} id={block.id}] {rendered_input}"


def _message_content_to_input(message: Message) -> List[InputTextItem]:
    if isinstance(message.content, str):
        return [InputTextItem(text=message.content)]
    content_items: List[InputTextItem] = []
    for block in message.content:
        if isinstance(block, TextBlock):
            content_items.append(InputTextItem(text=block.text))
            continue
        if isinstance(block, ToolResultBlock):
            content_items.append(InputTextItem(text=_tool_result_to_text(block)))
            continue
        if isinstance(block, ToolUseBlock):
            content_items.append(InputTextItem(text=_tool_use_to_text(block)))
            continue
        raise ValueError(
            f"Unsupported content block type: {getattr(block, 'type', None)}"
        )
    return content_items


def _map_message(message: Message) -> InputMessageItem:
    role = message.role
    if role == "assistant":
        role = "developer"
    return InputMessageItem(role=role, content=_message_content_to_input(message))


def map_anthropic_request_to_openai(request: MessagesRequest) -> OpenAIResponsesRequest:
    """Convert Anthropic Messages request into OpenAI Responses request."""

    instructions = _system_to_instructions(request.system)
    input_items = [_map_message(message) for message in request.messages]
    tools = None
    if request.tools:
        tools = [
            FunctionTool(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
                strict=False,
            )
            for tool in request.tools
        ]

    tool_choice: Optional[OpenAIToolChoice] = None
    if request.tool_choice is not None:
        if isinstance(request.tool_choice, str):
            tool_choice = request.tool_choice
        elif isinstance(request.tool_choice, ToolChoiceSpecific):
            tool_choice = ToolChoiceFunction(name=request.tool_choice.name)

    max_output_tokens: Optional[int] = None
    if request.max_tokens is not None and request.max_tokens >= 16:
        max_output_tokens = request.max_tokens

    payload = OpenAIResponsesRequest(
        model=resolve_openai_model(request.model),
        instructions=instructions,
        input=input_items,
        tools=tools,
        tool_choice=tool_choice,
        max_output_tokens=max_output_tokens,
    )
    return payload
