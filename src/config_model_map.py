"""Model mapping helpers for Anthropic->OpenAI model resolution."""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple


def normalize_model_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    return normalized or None


def parse_model_map_json(raw: str | None) -> Tuple[Dict[str, str], bool]:
    if not raw:
        return {}, False

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("MODEL_MAP_JSON must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("MODEL_MAP_JSON must be a JSON object")

    nested_models = parsed.get("models")
    if nested_models is not None:
        if not isinstance(nested_models, dict):
            raise ValueError("MODEL_MAP_JSON['models'] must be a JSON object")
        flat_keys = [k for k in parsed.keys() if k != "models"]
        if flat_keys:
            raise ValueError(
                "MODEL_MAP_JSON cannot contain both top-level mappings and a 'models' object"
            )
        mapping = nested_models
        nested_used = True
    else:
        mapping = parsed
        nested_used = False

    normalized_map: Dict[str, str] = {}
    seen_raw_keys: Dict[str, list[str]] = {}

    for raw_key, raw_value in mapping.items():
        normalized_key = normalize_model_key(raw_key)
        if normalized_key is None:
            raise ValueError("MODEL_MAP_JSON keys must be non-empty strings")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(
                f"MODEL_MAP_JSON value for '{raw_key}' must be a non-empty string"
            )
        if normalized_key in normalized_map:
            seen_raw_keys.setdefault(normalized_key, []).append(str(raw_key))
        else:
            seen_raw_keys.setdefault(normalized_key, []).append(str(raw_key))
            normalized_map[normalized_key] = raw_value

    collisions = {k: v for k, v in seen_raw_keys.items() if len(v) > 1}
    if collisions:
        parts = [f"{norm}: {raw_keys}" for norm, raw_keys in collisions.items()]
        raise ValueError(
            "MODEL_MAP_JSON has duplicate keys after normalization: " + "; ".join(parts)
        )

    return normalized_map, nested_used


def resolve_model_from_map(
    anthropic_model: Any,
    model_map: Dict[str, str],
) -> Tuple[str | None, str, str | None]:
    normalized_request = normalize_model_key(anthropic_model)

    match_type = "miss"
    resolved = None

    if normalized_request is not None:
        resolved = model_map.get(normalized_request)
        if resolved is not None:
            match_type = "exact"
        else:
            matches: list[tuple[str, str]] = [
                (k, v) for k, v in model_map.items() if normalized_request.startswith(k)
            ]
            if matches:
                max_len = max(len(k) for k, _ in matches)
                best = [(k, v) for k, v in matches if len(k) == max_len]
                if len(best) > 1:
                    keys = sorted(k for k, _ in best)
                    raise ValueError(
                        "MODEL_MAP_JSON prefix mapping is ambiguous for "
                        f"'{normalized_request}': {keys}"
                    )
                resolved = best[0][1]
                match_type = "prefix"

    return resolved, match_type, normalized_request

