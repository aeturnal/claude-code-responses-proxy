# Token Count Billing Alignment Report

- **Run at:** 2026-01-26T12:04:15.393912+00:00
- **Proxy base:** `http://localhost:8000`
- **OpenAI base:** `https://api.openai.com/v1`
- **Cases:** 2

## Case Results

| Case | Proxy input_tokens | OpenAI usage.input_tokens | Match |
| --- | --- | --- | --- |
| basic_with_tools | 52 | 52 | true |
| multi_message_no_tools | 33 | 33 | true |

## Sample Inputs and Outputs

### basic_with_tools

```json
{
  "model": "claude-3-5-sonnet-20240620",
  "system": "You are a helpful assistant.",
  "messages": [
    {
      "role": "user",
      "content": "Count these tokens please."
    }
  ],
  "tools": [
    {
      "name": "get_weather",
      "description": "Get weather for a city",
      "parameters": {
        "type": "object",
        "properties": {
          "city": {
            "type": "string"
          }
        },
        "required": [
          "city"
        ]
      }
    }
  ]
}
```

- **Proxy input_tokens:** 52
- **OpenAI usage.input_tokens:** 52
- **Match:** true

### multi_message_no_tools

```json
{
  "model": "claude-3-5-sonnet-20240620",
  "messages": [
    {
      "role": "user",
      "content": "Summarize this."
    },
    {
      "role": "assistant",
      "content": "Sure, share the text."
    },
    {
      "role": "user",
      "content": "OpenAI billing tokens should match."
    }
  ]
}
```

- **Proxy input_tokens:** 33
- **OpenAI usage.input_tokens:** 33
- **Match:** true

