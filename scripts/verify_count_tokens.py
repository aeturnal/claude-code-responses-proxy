# scripts/verify_count_tokens.py
import os
import json
import httpx
from src.mapping.anthropic_to_openai import map_anthropic_request_to_openai
from src.schema.anthropic import MessagesRequest
PROXY_BASE = os.getenv("PROXY_BASE", "http://localhost:8000")
OPENAI_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
anthropic_payload = {
    "model": "claude-3-5-sonnet-20240620",
    "system": "You are a helpful assistant.",
    "messages": [
        {"role": "user", "content": "Count these tokens please."}
    ],
    "tools": [
        {
            "name": "get_weather",
            "description": "Get weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        }
    ],
}
# 1) Proxy count_tokens
resp = httpx.post(f"{PROXY_BASE}/v1/messages/count_tokens", json=anthropic_payload)
resp.raise_for_status()
proxy_tokens = resp.json()["input_tokens"]
# 2) Map to OpenAI payload and call Responses API
mapped = map_anthropic_request_to_openai(MessagesRequest(**anthropic_payload))
openai_payload = mapped.model_dump(exclude_none=True)
openai_resp = httpx.post(
    f"{OPENAI_URL}/responses",
    headers={"Authorization": f"Bearer {OPENAI_KEY}"},
    json=openai_payload,
)
openai_resp.raise_for_status()
openai_tokens = openai_resp.json()["usage"]["input_tokens"]
print("Proxy count_tokens:", proxy_tokens)
print("OpenAI usage.input_tokens:", openai_tokens)
print("Match:", proxy_tokens == openai_tokens)
