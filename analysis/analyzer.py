from __future__ import annotations
from collections import defaultdict
from pathlib import Path

from stateforge.analysis.flask_adapter import extract_flask
from stateforge.analysis.openapi_adapter import extract_connexion
from stateforge.analysis.selector import select
from stateforge.core.model import AppModel, Invariant, StateCandidate, StateVar
from stateforge.solving.llm.heuristic import label_rule_based


def analyze(target_dir: str | Path, framework: str = "flask") -> AppModel:
    target_dir = Path(target_dir)
    if framework == "flask":
        model = extract_flask(target_dir)
    elif framework == "connexion":
        model = extract_connexion(target_dir)
    elif framework == "django":
        from stateforge.analysis.django_adapter import extract_django
        model = extract_django(target_dir)
    else:
        raise ValueError(f"unknown framework: {framework}")

    
    domains = _domains(model)
    from stateforge.solving.llm.lifting import label, relate, apply_lift_result
    from stateforge.solving.llm.provider import Provider
    provider = Provider.from_env()
    svs, lift = label(model.candidates, domains, provider=provider)
    model.state_vars = select(svs)

    
    sec = [sv for sv in model.state_vars if sv.security_relevant]
    if sec:
        rel = relate(sec, model.endpoints, provider=provider)
        apply_lift_result(model, rel)  
    model.invariants = derive_invariants(model)
    return model

def _domains(model: AppModel) -> dict[str, list[str]]:
    
    values: dict[str, list[str]] = defaultdict(list)
    for ep in model.endpoints:
        for pre in ep.preconditions:
            if pre.value and pre.var != "Session.authed_as":
                if pre.value not in values[pre.var]:
                    values[pre.var].append(pre.value)
        for eff in ep.effects:
            if eff.value and eff.var != "Session.authed_as":
                if eff.value not in values[eff.var]:
                    values[eff.var].append(eff.value)
    return dict(values)


def derive_invariants(model: AppModel) -> list[Invariant]:
    
    create_value: dict[str, str] = {}
    transitions: dict[str, set[tuple[str, str]]] = defaultdict(set)
    appearance: dict[str, list[str]] = defaultdict(list)
    bool_vars: dict[str, set[str]] = defaultdict(set)
    bool_write: dict[str, set[str]] = defaultdict(set)
    def seen(var: str, value: str) -> None:
        if value not in appearance[var]:
            appearance[var].append(value)
    for ep in model.endpoints:  
        pres = {p.var: p.value for p in ep.preconditions if p.value}
        for pre in ep.preconditions:
            if pre.value:
                seen(pre.var, pre.value)
            elif pre.op in ("truthy", "falsy"):
                
                bool_vars[pre.var] |= {"truthy" if pre.op == "truthy" else "falsy"}
        for eff in ep.effects:
            if eff.op != "set" or eff.value is None:
                continue
            seen(eff.var, eff.value)
            if eff.var not in create_value:
                create_value[eff.var] = eff.value
            if eff.var in pres and pres[eff.var] != eff.value:
                transitions[eff.var].add((pres[eff.var], eff.value))
            elif eff.var not in pres and create_value.get(eff.var) != eff.value:
                transitions[eff.var].add((create_value[eff.var], eff.value))
            bool_write[eff.var].add(eff.value)
    invs: list[Invariant] = []
    for var, dom in appearance.items():
        if len(dom) < 2:
            continue
        entity, _, attr = var.partition(".")
        
        incoming = {w for _, w in transitions.get(var, set())}
        order = dom
        for i, v in enumerate(order):
            if v == create_value.get(var) or v in incoming or i == 0:
                continue
            transitions[var].add((order[i - 1], v))
        inv = Invariant(
            entity=entity, attr=attr,
            legal_transitions=sorted(transitions.get(var, set())),
        )
        if set(dom) <= {"0", "1", "True", "False"} and all(
            w in ("1", "True") for _, w in inv.legal_transitions
        ):
            inv.one_way = [attr]
        invs.append(inv)

    
    for var, ops in bool_vars.items():
        if var in {i.var for i in invs}:
            continue
        writes = bool_write.get(var, set())
        if writes and writes <= {"1", "True"}:
            entity, _, attr = var.partition(".")
            invs.append(Invariant(
                entity=entity, attr=attr,
                legal_transitions=[("False", "True")],
                one_way=[attr],
            ))
    return invs
