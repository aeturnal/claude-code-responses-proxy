# Phase 6: Token Count Billing Alignment Verification

## Purpose
Verify `/v1/messages/count_tokens` returns input token counts that match OpenAI billing usage (`usage.input_tokens`) for the mapped request payloads.

## Prerequisites

- Local proxy running and reachable at `PROXY_BASE` (default: `http://localhost:8000`).
- OpenAI API key with access to the Responses API.

## Environment Variables

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | Yes | — | OpenAI API key used to call `https://api.openai.com/v1/responses`. |
| `OPENAI_BASE_URL` | No | `https://api.openai.com/v1` | Override OpenAI base URL if needed. |
| `PROXY_BASE` | No | `http://localhost:8000` | Base URL for the proxy under test. |

## Run the Harness

```bash
python scripts/verify_count_tokens.py
```

## Expected Output

The script prints per-case comparisons and exits non-zero if any case mismatches. A report is always written to:

```
.planning/phases/06-token-count-billing-alignment-verification/06-token-count-billing-alignment-report.md
```

### Sample Output

```
basic_with_tools: proxy=52 openai=52 match=True
multi_message_no_tools: proxy=33 openai=33 match=True
Report written to: .planning/phases/06-token-count-billing-alignment-verification/06-token-count-billing-alignment-report.md
```

## Evidence

- Review the report file for a table of case results and embedded sample payloads with observed token counts.
- Confirm all cases show `match=true`.
