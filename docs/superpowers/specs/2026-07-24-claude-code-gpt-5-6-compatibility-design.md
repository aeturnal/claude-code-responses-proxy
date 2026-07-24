# Claude Code and GPT-5.6 Compatibility Design

## Goal

Update the proxy so current Claude Code traffic can use GPT-5.6 Sol, Terra, and
Luna through the ChatGPT Codex credential backend. Preserve the repository's
text, function-tool, streaming, error-envelope, and privacy conventions.

## Scope

The target is current Claude Code request patterns, not broad parity with every
current Anthropic Messages API feature. Images, documents, MCP connectors,
server-side tools, realtime, and generic full-Messages-API parity remain out of
scope.

## Model Routing

The configuration layer provides the default current-family route:

| Claude model family | GPT-5.6 target |
| --- | --- |
| Fable 5 and Opus 5 | Sol |
| Sonnet 5 | Terra |
| Haiku 4.5 | Luna |

`MODEL_MAP_JSON` remains the higher-priority operator override. An unknown
Anthropic model falls back to Terra. Model names are retained in Anthropic
responses and logs continue to identify both incoming and resolved model names.

## Request Compatibility

The Anthropic schema accepts the current Claude Code fields needed for the
supported workflow. Each field has an explicit disposition:

- Faithfully map values with equivalent Responses API semantics.
- Preserve harmless client metadata only when it has a defined proxy purpose.
- Return an Anthropic-formatted unsupported-feature error when safe translation
  is impossible.

New translation logic belongs in the schema and mapping layers. Codex-specific
requirements remain in transport: Codex authentication, `store: false`,
upstream streaming, fallback instructions, assistant `output_text` history, and
removal of fields the backend rejects.

## Reasoning Controls

Map Anthropic `output_config.effort` to the same-valued GPT-5.6
`reasoning.effort` for the mutually supported levels: `low`, `medium`, `high`,
`xhigh`, and `max`. The proxy uses an explicit fallback reasoning policy rather
than silently relying on the GPT-5.6 `medium` default.

Adaptive Claude thinking is supported through this effort mapping. Legacy manual
thinking with `thinking.type: "enabled"` and `budget_tokens` has no equivalent
token-budget contract in Responses; the proxy returns a clear compatibility
error rather than silently choosing an arbitrary reasoning level.

The proxy does not emit OpenAI reasoning as Anthropic `thinking` blocks. The
providers have incompatible signed/encrypted continuation formats, and a lossy
conversion would break later conversation or tool turns.

## Response and Streaming Compatibility

Keep the existing Anthropic response and SSE contracts unchanged for text,
function calls, citations, stop reasons, and normalized usage. Streaming remains
incremental and must finish every started content block before `message_delta`
and `message_stop`. OpenAI reasoning content remains internal and is not
presented as a Claude thinking block.

## Diagnostics and Validation

Validation failures receive the existing Anthropic error envelope and a
redacted structured log entry. Diagnostic logs must identify the rejected field
or unsupported compatibility feature without recording raw prompts, tool output,
or credentials.

## Verification

Add focused deterministic tests beside existing mapper, transport, response, and
stream tests:

- current-family routing and operator-override precedence;
- effort mapping, fallback policy, and manual-thinking rejection;
- supported current Claude Code content blocks and fields;
- Anthropic HTTP and SSE error envelopes for validation failures;
- regression coverage for existing tool order, JSON deltas, stop reasons, usage,
  redaction, and Codex payload rewrites.

Provide an opt-in live Codex smoke test for the three GPT-5.6 model IDs and
allowed reasoning settings. The test reports backend/account rejection clearly;
it is not part of the normal deterministic suite.

## Non-Goals

- Fabricating Anthropic-signed thinking blocks from OpenAI reasoning.
- Converting manual thinking budgets to arbitrary GPT reasoning levels.
- Adding images, files, documents, audio, realtime, or external MCP support.
- Removing existing model-map overrides or historical model compatibility.
