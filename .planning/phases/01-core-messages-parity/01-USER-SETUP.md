# Phase 1: User Setup Required

**Generated:** 2026-01-26
**Phase:** 01-core-messages-parity
**Status:** Incomplete

Complete these items for the OpenAI Responses integration to function. Claude automated everything possible; these items require human access to external dashboards/accounts.

## Environment Variables

| Status | Variable | Source | Add to |
|--------|----------|--------|--------|
| [ ] | `OPENAI_API_KEY` | OpenAI Dashboard → API keys | `.env` |

## Verification

After completing setup, verify with:

```bash
python -c "import os; print('OPENAI_API_KEY set' if os.getenv('OPENAI_API_KEY') else 'missing')"
```

Expected results:
- Output shows `OPENAI_API_KEY set`

---

**Once all items complete:** Mark status as "Complete" at top of file.
