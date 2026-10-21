from __future__ import annotations
import json
from stateforge.fuzzing.mutation_hint import MutationHint

_SECTION = {"QUERY": "query", "FORM": "form", "JSON": "json",
            "HEADER": "header", "COOKIE": "cookie"}


class MutationError(ValueError):
    pass


def serialize_for(kind: str, value) -> object:
    
    return str(value) if kind in ("QUERY", "FORM", "HEADER", "COOKIE") else value


def apply_hint(seed: dict, hint: MutationHint) -> dict:
    import copy
    if hint.reason != "solved" or hint.target_value is None:
        raise MutationError(f"hint 未求解: {hint.reason}")
    section = _SECTION.get(hint.source_kind)
    if section is None or section not in seed:
        raise MutationError(f"种子缺少段: {hint.source_kind}")
    out = copy.deepcopy(seed)
    out[section][hint.source_key] = serialize_for(hint.source_kind,
                                                  hint.target_value)
    return out


def seed_to_bytes(seed: dict) -> bytes:
    return json.dumps(seed, ensure_ascii=False, sort_keys=True).encode("utf-8")
