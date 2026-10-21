from __future__ import annotations
from stateforge.core.model import StateCandidate, StateVar

def label_rule_based(
    candidates: list[StateCandidate], domains: dict[str, list[str]]
) -> list[StateVar]:
    
    out: dict[str, StateVar] = {}
    for cand in candidates:
        entity, _, attr = cand.var.partition(".")
        domain = domains.get(cand.var)
        if cand.var not in out:
            out[cand.var] = StateVar(
                entity=entity,
                attr=attr,
                kind="session" if entity == "Session" else "db_column",
                domain=domain,
                label="irrelevant",
                rationale="[no-llm] 无 LLM 且缓存未命中,不猜语义",
                anchors=[(cand.file, cand.line)] if cand.line else [],
            )
        else:
            sv = out[cand.var]
            if domain and (not sv.domain or len(domain) > len(sv.domain)):
                sv.domain = domain
            if (cand.file, cand.line) not in sv.anchors and cand.line:
                sv.anchors.append((cand.file, cand.line))
    return list(out.values())
