# Haiku-to-Luna Maximum Thinking Design

## Goal

Allow Claude Code requests for Claude Haiku 4.5 to complete through the proxy
without losing their normal manual-thinking intent.

## Observed behavior

Claude Code sends every tested Haiku request with:

```json
{
  "thinking": {
    "type": "enabled",
    "budget_tokens": 31999,
    "display": "omitted"
  }
}
```

This is present in the inbound request before the proxy's mapper runs. Claude
Code exposes no no-thinking effort option for Haiku.

## Mapping policy

- If the inbound model is Claude Haiku 4.5 and `thinking.type` is `enabled`,
  map to `gpt-5.6-luna` with `reasoning.effort: "max"`.
- An explicit `thinking.type: "disabled"` continues to map to OpenAI
  `reasoning.effort: "none"` for all supported GPT-5.6 models.
- Manual thinking budgets from models other than Claude Haiku 4.5 continue to
  receive the existing compatibility error; no generic numeric budget-to-effort
  conversion is introduced.
- Existing `output_config.effort` behavior remains unchanged outside the Haiku
  manual-thinking case.

## Implementation and verification

Change only the reasoning mapper and focused mapper/API tests. Verify that
Haiku's manual budget maps to Luna `max`, non-Haiku manual budgets still fail,
and the full test suite remains green.
