# Phase 02: Token Counting Alignment - Research

**Researched:** 2026-01-25
**Domain:** Token counting (Anthropic Messages API compatibility + OpenAI billing alignment)
**Confidence:** MEDIUM

## Summary

This phase requires implementing `/v1/messages/count_tokens` so it behaves like Anthropic’s count-tokens endpoint, but with token counts aligned to OpenAI’s billing rules. The key is to reuse the exact same request normalization and mapping used by `/v1/messages` (system prompt, tool definitions, message content blocks), then compute token usage using OpenAI’s documented tokenization approach (tiktoken + model-specific overheads + tool-definition accounting).

The standard approach is to tokenize with **tiktoken** (official OpenAI tokenizer) and apply OpenAI’s reference counting algorithm for chat messages (tokens-per-message, tokens-per-name) plus tool-definition overhead rules. OpenAI explicitly warns that token-counting formulas can change by model; use **model snapshots** and fallbacks as in the OpenAI cookbook example, and treat counts as estimates where docs warn.

**Primary recommendation:** Reuse the `/v1/messages` mapping pipeline to produce an OpenAI-style payload, then count tokens with tiktoken using the OpenAI cookbook’s chat + tools formulas (per model), returning only the input token count.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| tiktoken (Python) | 0.12.0 | Tokenization for OpenAI models | Official OpenAI tokenizer; provides `encoding_for_model` and BPE-compatible tokenization used for billing | 

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| OpenAI Cookbook token counting reference | 2022-12-16 (archived) | Reference algorithm for chat + tools token counting | Use to mirror OpenAI billing rules (tokens-per-message + tool schema overhead) | 

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| tiktoken (Python) | Language-specific tokenizers (e.g., tiktoken-go, jtokkit) | Only relevant if service language changes; Python tiktoken is canonical | 

**Installation:**
```bash
pip install tiktoken
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── handlers/          # HTTP handlers (count_tokens endpoint)
├── mapping/           # Anthropic <-> OpenAI normalization
├── token_counting/    # OpenAI-aligned counting utilities
└── schema/            # request/response models
```

### Pattern 1: Shared Normalization Pipeline
**What:** Reuse the same normalization/mapping logic as `/v1/messages` to produce an OpenAI-like payload (messages, tools, system prompt) before token counting.
**When to use:** Always; required by TOK-02.
**Example:**
```python
# Source: https://docs.anthropic.com/en/api/messages-count-tokens
# (Use the same system/messages/tools structure as Messages API)
payload = {
    "model": model,
    "system": system,
    "messages": messages,
    "tools": tools,
}
# Normalize to the same OpenAI-format payload used by /v1/messages,
# then count tokens against the normalized content.
```

### Pattern 2: OpenAI Chat Token Formula (Messages)
**What:** Apply model-specific per-message overhead plus content tokenization.
**When to use:** For OpenAI-aligned counting of system/user/assistant content blocks.
**Example:**
```python
# Source: https://developers.openai.com/cookbook/examples/how_to_count_tokens_with_tiktoken
def num_tokens_from_messages(messages, model="gpt-4o-mini-2024-07-18"):
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("o200k_base")
    if model in {"gpt-3.5-turbo-0125", "gpt-4-0613", "gpt-4o-2024-08-06", "gpt-4o-mini-2024-07-18"}:
        tokens_per_message = 3
        tokens_per_name = 1
    else:
        # fall back to the closest known snapshot
        return num_tokens_from_messages(messages, model="gpt-4o-mini-2024-07-18")
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3  # reply primer
    return num_tokens
```

### Pattern 3: Tool Schema Token Accounting
**What:** Add tool-definition overhead tokens in addition to message tokens.
**When to use:** When tools are provided in the request (TOK-02).
**Example:**
```python
# Source: https://developers.openai.com/cookbook/examples/how_to_count_tokens_with_tiktoken
# Tool schema overhead depends on model family (gpt-4o vs gpt-4).
# Count function metadata and parameters using encoding.encode().
```

### Anti-Patterns to Avoid
- **Counting pre-normalized Anthropic payload:** Must count the OpenAI-mapped payload to stay aligned with `/v1/messages` and OpenAI billing.
- **Ignoring tool schema tokens:** OpenAI bills for tool definitions; omitting them undercounts.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tokenization | Custom BPE or whitespace counters | `tiktoken` | OpenAI billing uses tokenizer-specific BPE; custom tokenizers will drift | 
| Tool schema counting | Ad-hoc token rules | OpenAI cookbook tool-counting algorithm | Tool definitions add non-obvious overhead tokens; reference algorithm matches API | 
| Model encoding selection | Hardcoded encoding | `tiktoken.encoding_for_model()` with fallback | Encoding varies by model family; wrong encoding = wrong billing | 

**Key insight:** Token counting for OpenAI billing is model- and format-dependent; always use OpenAI’s tokenizer and reference rules.

## Common Pitfalls

### Pitfall 1: Wrong model encoding
**What goes wrong:** Token counts deviate from OpenAI billing.
**Why it happens:** Using a default encoding instead of `encoding_for_model` or a proper fallback.
**How to avoid:** Always call `encoding_for_model`, fallback to `o200k_base` only when model is unknown.
**Warning signs:** Counts differ from OpenAI API usage for the same prompt.

### Pitfall 2: Ignoring per-message overhead
**What goes wrong:** Consistently undercounting tokens.
**Why it happens:** Only counting content tokens.
**How to avoid:** Apply tokens-per-message and reply primer constants from the OpenAI reference function.
**Warning signs:** Counts are smaller by a fixed offset per message.

### Pitfall 3: Tool definitions not counted
**What goes wrong:** Underbilling preflight counts when tools are present.
**Why it happens:** Tool schemas are not included in the token count.
**How to avoid:** Add tool-definition overhead per OpenAI cookbook rules.
**Warning signs:** Requests with tools show lower counts than OpenAI usage.

### Pitfall 4: Mismatch with `/v1/messages` mapping
**What goes wrong:** Token counts for `count_tokens` differ from actual message behavior.
**Why it happens:** Separate normalization logic for count_tokens.
**How to avoid:** Reuse the same mapping/normalization pipeline used by `/v1/messages`.
**Warning signs:** Same input yields different counts vs actual message request.

## Code Examples

Verified patterns from official sources:

### Load encoding by model and count tokens
```python
# Source: https://raw.githubusercontent.com/openai/tiktoken/main/README.md
import tiktoken
enc = tiktoken.encoding_for_model("gpt-4o")
token_count = len(enc.encode("hello world"))
```

### Count tokens for chat messages (OpenAI reference)
```python
# Source: https://developers.openai.com/cookbook/examples/how_to_count_tokens_with_tiktoken
def num_tokens_from_messages(messages, model="gpt-4o-mini-2024-07-18"):
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("o200k_base")
    tokens_per_message = 3
    tokens_per_name = 1
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3
    return num_tokens
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Simple word/char counts | tiktoken with model-specific encoding | 2022+ (tiktoken adoption) | Accurate billing-aligned counts | 
| Generic GPT-2 encoders | Model-aware `encoding_for_model()` | Ongoing | Prevents drift across model families | 

**Deprecated/outdated:**
- Counting tokens by character/word length — not aligned with OpenAI billing (BPE-based).

## Open Questions

1. **Exact tool token overhead for newest OpenAI models**
   - What we know: OpenAI cookbook provides model-specific constants for gpt-4/gpt-4o families.
   - What's unclear: Whether newer snapshots alter overhead constants.
   - Recommendation: Validate against real OpenAI API usage for target models; update constants if needed.

2. **Handling non-text content (images/documents) in OpenAI-aligned counting**
   - What we know: Anthropic count_tokens supports images/documents; OpenAI has separate accounting for vision inputs.
   - What's unclear: How the proxy maps these inputs for OpenAI billing alignment.
   - Recommendation: If non-text is supported in `/v1/messages`, mirror the same mapping and use OpenAI’s latest vision token rules; otherwise document limitations.

## Sources

### Primary (HIGH confidence)
- https://raw.githubusercontent.com/openai/tiktoken/main/README.md — tiktoken usage and encoding selection
- https://docs.anthropic.com/en/api/messages-count-tokens — Anthropic count_tokens request schema
- https://docs.claude.com/en/docs/build-with-claude/token-counting — Anthropic token counting guidance

### Secondary (MEDIUM confidence)
- https://developers.openai.com/cookbook/examples/how_to_count_tokens_with_tiktoken — OpenAI token counting formulas (archived; model-specific constants)
- https://pypi.org/pypi/tiktoken/json — tiktoken version (0.12.0)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — official tokenizer + PyPI version
- Architecture: MEDIUM — derived from official schemas + reference counting algorithms
- Pitfalls: MEDIUM — inferred from OpenAI/Anthropic guidance and known tokenization behavior

**Research date:** 2026-01-25
**Valid until:** 2026-02-24 (30 days; token rules evolve)
