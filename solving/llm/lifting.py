from __future__ import annotations
import json
from pathlib import Path
from pydantic import BaseModel, Field, ValidationError
from stateforge.core.model import Endpoint, StateCandidate, StateVar
from stateforge.solving.llm import cache
from stateforge.solving.llm.heuristic import label_rule_based
from stateforge.solving.llm.provider import Provider

PROMPT_VERSION = "v1"
_PROMPTS = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
_LABEL_SYSTEM = _PROMPTS.split("## label(system)")[1].split("## relate(system)")[0].strip()
_RELATE_SYSTEM = _PROMPTS.split("## relate(system)")[1].strip()

VALID_LABELS = {"authn", "authz", "ownership", "money", "workflow", "single_use", "irrelevant"}


class ExtraTransition(BaseModel):
    endpoint: str
    var: str
    frm: str = Field(alias="from")
    to: str

    model_config = {"populate_by_name": True}


class AuthChain(BaseModel):
    
    endpoint: str                     
    direction: str                    
    rationale: str = ""


class CrossEntityInvariant(BaseModel):
    vars: list[str]
    rule: str

class LiftResult(BaseModel):
    source: str = "heuristic"            
    role_hierarchy: dict[str, list[str]] = Field(default_factory=dict)
    extra_transitions: list[ExtraTransition] = Field(default_factory=list)
    cross_entity_invariants: list[CrossEntityInvariant] = Field(default_factory=list)
    auth_chains: list[AuthChain] = Field(default_factory=list)  
    label_log: list[dict] = Field(default_factory=list)   
    meta: dict = Field(default_factory=dict)             




def label(candidates: list[StateCandidate], domains: dict[str, list[str]],
          provider: Provider | None = None) -> tuple[list[StateVar], LiftResult]:
    facts = [
        {"var": c.var, "ops": c.ops, "source": c.source,
         "domain": domains.get(c.var), "evidence": c.evidence[:160]}
        for c in candidates
    ]

    
    cached_raw = cache.get({"kind": "label", "facts": facts}, PROMPT_VERSION)
    if cached_raw is not None:
        parsed = _parse_labels(cached_raw, facts)
        if parsed is not None:
            return _apply_labels(parsed, candidates, domains,
                                 LiftResult(source="llm:cache",
                                            meta={"from": "cache"}))
    
    if provider is None:
        return label_rule_based(candidates, domains), LiftResult(source="no-llm")

    
    raw = _cached_complete(provider, "label", facts, _LABEL_SYSTEM)
    parsed = _parse_labels(raw, facts)
    if parsed is None:  
        raw = _cached_complete(provider, "label", facts,
                               _LABEL_SYSTEM + "\n(previous answer was not valid JSON — output ONLY the JSON array)",
                               refresh=True)
        parsed = _parse_labels(raw, facts)
    if parsed is None:  
        return label_rule_based(candidates, domains), LiftResult(
            source="no-llm", meta={"fallback": "schema_violation"},
        )
    return _apply_labels(parsed, candidates, domains,
                         LiftResult(source=f"llm:{provider.kind}:{provider.model}",
                                    meta={"temperature": 0.0, "prompt": PROMPT_VERSION,
                                          "model": provider.model}))


def _apply_labels(parsed: list[dict], candidates: list[StateCandidate],
                  domains: dict[str, list[str]], lift: LiftResult
                  ) -> tuple[list[StateVar], LiftResult]:
    
    by_var = {p["var"]: p for p in parsed}
    out = label_rule_based(candidates, domains)  
    for sv in out:
        hit = by_var.get(sv.var)
        if hit:
            sv.label = hit["label"]
            sv.rationale = f"[{lift.source}] {hit['rationale']}"
    lift.label_log = [{"var": p["var"], "label": p["label"],
                       "confidence": p.get("confidence")} for p in parsed]
    return out, lift


def _parse_labels(raw: str, facts: list[dict]) -> list[dict] | None:
    try:
        arr = json.loads(_strip_fences(raw))
    except json.JSONDecodeError:
        return None
    if not isinstance(arr, list):
        return None
    want_vars = {f["var"] for f in facts}
    got = set()
    out = []
    for item in arr:
        if not isinstance(item, dict) or item.get("var") not in want_vars:
            continue
        if item.get("label") not in VALID_LABELS:
            continue
        if item["var"] in got:
            continue
        got.add(item["var"])
        out.append(item)
    return out if got == want_vars else None


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _cached_complete(provider: Provider, kind: str, facts, system: str,
                     refresh: bool = False) -> str:
    if not refresh:
        hit = cache.get({"kind": kind, "facts": facts}, PROMPT_VERSION)
        if hit is not None:
            return hit
    raw = provider.complete(system, json.dumps(facts, ensure_ascii=False))
    cache.put({"kind": kind, "facts": facts}, PROMPT_VERSION, raw)
    return raw





def relate(relevant_vars: list[StateVar], endpoints: list[Endpoint],
           provider: Provider | None = None) -> LiftResult:
    
    if not relevant_vars:
        return LiftResult(source="no-llm")
    facts = {
        "vars": [
            {"var": sv.var, "label": sv.label, "domain": sv.domain}
            for sv in relevant_vars
        ],
        "endpoints": [
            {"route": f"{ep.methods[0]} {ep.route}",
             "pre": [[p.var, p.op, p.value] for p in ep.preconditions],
             "eff": [[e.var, e.value] for e in ep.effects],
             "observes": ep.observes[:6]}
            for ep in endpoints
        ],
    }
    cached_raw = cache.get({"kind": "relate", "facts": facts}, PROMPT_VERSION)
    if cached_raw is not None:
        return _parse_relate(cached_raw, LiftResult(source="llm:cache"))

    if provider is None:
        return LiftResult(source="no-llm")

    raw = _cached_complete(provider, "relate", facts, _RELATE_SYSTEM)
    return _parse_relate(raw, LiftResult(
        source=f"llm:{provider.kind}:{provider.model}",
        meta={"temperature": 0.0, "prompt": PROMPT_VERSION, "model": provider.model}))


def _parse_relate(raw: str, lift: LiftResult) -> LiftResult:
    try:
        data = json.loads(_strip_fences(raw))
        lift.role_hierarchy = data.get("role_hierarchy") or {}
        lift.extra_transitions = [ExtraTransition.model_validate(t)
                                  for t in data.get("extra_transitions") or []]
        lift.cross_entity_invariants = [CrossEntityInvariant.model_validate(i)
                                        for i in data.get("cross_entity_invariants") or []]
        lift.auth_chains = [AuthChain.model_validate(a)
                            for a in data.get("auth_chains") or []]
        return lift
    except (json.JSONDecodeError, ValidationError):
        return LiftResult(source="no-llm", meta={"fallback": "schema_violation"})


def apply_lift_result(model, lift: LiftResult) -> int:
    
    from stateforge.core.model import Effect, Precondition, StateCandidate

    added = 0
    sec_entities = {sv.var.split(".")[0] for sv in model.state_vars
                    if sv.security_relevant}

    
    
    
    
    for chain in lift.auth_chains:
        route = chain.endpoint
        for ep in model.endpoints:
            if f"{ep.methods[0]} {ep.route}" == route or ep.route == route:
                if chain.direction == "produce":
                    has_auth = any(e.var == "Session.authed_as" for e in ep.effects)
                    other_sec_effs = [
                        e for e in ep.effects
                        if e.var != "Session.authed_as"
                        and e.var.split(".")[0] in sec_entities
                    ]
                    if not has_auth and not other_sec_effs:
                        ep.effects.append(Effect(
                            var="Session.authed_as", op="set", key="username",
                            file=ep.file, line=ep.line))
                        added += 1
                elif chain.direction == "require":
                    if not any(p.var == "Session.authed_as" for p in ep.preconditions):
                        ep.preconditions.append(Precondition(
                            var="Session.authed_as", op="truthy",
                            file=ep.file, line=ep.line))
                        added += 1
                elif chain.direction == "clear":
                    if not any(e.var == "Session.authed_as" and e.op == "clear"
                               for e in ep.effects):
                        ep.effects.append(Effect(
                            var="Session.authed_as", op="clear",
                            file=ep.file, line=ep.line))
                        added += 1
                break

    
    if sec_entities:
        auth_ep_routes = {"/auth/register", "/auth/login", "/"}
        for ep in model.endpoints:
            has_pre = any(p.var == "Session.authed_as" for p in ep.preconditions)
            is_public = ep.route in auth_ep_routes or ep.route.startswith("/auth/")
            touches_sec = any(
                e.var.split(".")[0] in sec_entities for e in ep.effects
            ) or any(
                p.var.split(".")[0] in sec_entities for p in ep.preconditions
            )
            if touches_sec and not has_pre and not is_public:
                ep.preconditions.append(Precondition(
                    var="Session.authed_as", op="truthy",
                    file=ep.file, line=ep.line))
                added += 1

    
    if added:
        from stateforge.core.model import StateVar
        if not any(c.var == "Session.authed_as" for c in model.candidates):
            model.candidates.append(StateCandidate(
                var="Session.authed_as", entity="Session", attr="authed_as",
                ops=["write", "read"],
                evidence="LLM auth_chains + structural inference",
                source="session_access", file="", line=0))
        if not any(sv.var == "Session.authed_as" for sv in model.state_vars):
            model.state_vars.append(StateVar(
                entity="Session", attr="authed_as", kind="session",
                label="authn", security_relevant=True,
                rationale=f"[{lift.source}] LLM auth chain + structural inference"))
    return added
