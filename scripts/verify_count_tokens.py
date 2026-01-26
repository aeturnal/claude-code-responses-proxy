# scripts/verify_count_tokens.py
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import httpx

from src.mapping.anthropic_to_openai import map_anthropic_request_to_openai
from src.schema.anthropic import MessagesRequest

PROXY_BASE = os.getenv("PROXY_BASE", "http://localhost:8000")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
CASE_PATH = Path(__file__).resolve().parent / "fixtures" / "token_count_cases.json"
REPORT_PATH = (
    Path(__file__).resolve().parents[1]
    / ".planning/phases/06-token-count-billing-alignment-verification"
    / "06-token-count-billing-alignment-report.md"
)
REQUEST_TIMEOUT = 30.0


def _load_cases(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Fixture file not found: {path}")
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "cases" in data:
        cases = data["cases"]
    elif isinstance(data, list):
        cases = data
    else:
        raise ValueError("Fixture file must be a list or contain a 'cases' array")
    if not cases:
        raise ValueError("Fixture file contains no cases")
    return cases


def _write_report(results: List[Dict[str, Any]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    lines: List[str] = [
        "# Token Count Billing Alignment Report",
        "",
        f"- **Run at:** {now}",
        f"- **Proxy base:** `{PROXY_BASE}`",
        f"- **OpenAI base:** `{OPENAI_URL}`",
        f"- **Cases:** {len(results)}",
        "",
        "## Case Results",
        "",
        "| Case | Proxy input_tokens | OpenAI usage.input_tokens | Match |",
        "| --- | --- | --- | --- |",
    ]
    for result in results:
        lines.append(
            "| {name} | {proxy} | {openai} | {match} |".format(
                name=result["name"],
                proxy=result["proxy_tokens"],
                openai=result["openai_tokens"],
                match=str(result["match"]).lower(),
            )
        )

    lines.extend(["", "## Sample Inputs and Outputs", ""])
    for result in results[:2]:
        payload_json = json.dumps(result["payload"], indent=2, ensure_ascii=False)
        lines.extend(
            [
                f"### {result['name']}",
                "",
                "```json",
                payload_json,
                "```",
                "",
                f"- **Proxy input_tokens:** {result['proxy_tokens']}",
                f"- **OpenAI usage.input_tokens:** {result['openai_tokens']}",
                f"- **Match:** {str(result['match']).lower()}",
                "",
            ]
        )

    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> int:
    if not OPENAI_KEY:
        print(
            "OPENAI_API_KEY is not set. Set it before running this script.\n"
            "Example: export OPENAI_API_KEY=sk-..."
        )
        return 1

    cases = _load_cases(CASE_PATH)
    results: List[Dict[str, Any]] = []
    for case in cases:
        name = case.get("name")
        payload = case.get("payload")
        if not name or not payload:
            raise ValueError("Each case must include 'name' and 'payload'")

        resp = httpx.post(
            f"{PROXY_BASE}/v1/messages/count_tokens",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        proxy_tokens = resp.json()["input_tokens"]

        mapped = map_anthropic_request_to_openai(MessagesRequest(**payload))
        openai_payload = mapped.model_dump(exclude_none=True)
        openai_resp = httpx.post(
            f"{OPENAI_URL}/responses",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            json=openai_payload,
            timeout=REQUEST_TIMEOUT,
        )
        openai_resp.raise_for_status()
        openai_tokens = openai_resp.json()["usage"]["input_tokens"]

        results.append(
            {
                "name": name,
                "payload": payload,
                "proxy_tokens": proxy_tokens,
                "openai_tokens": openai_tokens,
                "match": proxy_tokens == openai_tokens,
            }
        )

    _write_report(results)

    all_match = all(result["match"] for result in results)
    for result in results:
        print(
            f"{result['name']}: proxy={result['proxy_tokens']} openai={result['openai_tokens']} match={result['match']}"
        )
    print(f"Report written to: {REPORT_PATH}")
    return 0 if all_match else 1


if __name__ == "__main__":
    sys.exit(main())
