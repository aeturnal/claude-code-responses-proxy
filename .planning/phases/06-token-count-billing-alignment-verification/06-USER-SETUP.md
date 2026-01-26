# Phase 6: User Setup Required

**Generated:** 2026-01-26
**Phase:** 06-token-count-billing-alignment-verification
**Status:** Incomplete

Complete these items for the verification harness to run successfully. Claude automated everything possible; these items require human access to external dashboards/accounts.

## Environment Variables

| Status | Variable | Source | Add to |
|--------|----------|--------|--------|
| [ ] | `OPENAI_API_KEY` | OpenAI Dashboard → API keys | `.env` or shell environment |

## Verification

After completing setup, verify with:

```bash
python scripts/verify_count_tokens.py
```

Expected results:
- Script prints per-case comparisons
- Report file written to `.planning/phases/06-token-count-billing-alignment-verification/06-token-count-billing-alignment-report.md`
- Exit code is 0 when all cases match

---

**Once all items complete:** Mark status as "Complete" at top of file.
