from __future__ import annotations
import networkx as nx
from stateforge.core.model import AppModel, PlanSegment, PlanStep
from stateforge.state.planning.goals import GoalSpec, auth_provisioning
from stateforge.state.planning.compat import (
    JSON_FILL as _JSON_FILL,
    ensure_auth as _ensure_auth,
    produces_token as _produces_token,
    resource_completion as _resource_completion,
    uses_token as _uses_token,
)
def _pick_producer(producers: list[str], sstg: nx.MultiDiGraph,
                   seen_atoms: set[str], drop: set[str]) -> str:
    
    def cost(action: str) -> tuple[int, int, str]:
        reqs = [v for _, v, d in sstg.out_edges(action, data=True)
                if d.get("kind") == "requires"]
        unmet = [v for v in reqs
                 if v not in seen_atoms
                 and v.split("=", 1)[0] not in drop]
        return len(unmet), len(reqs), action

    return min(producers, key=cost)


def plan_backward(model: AppModel, sstg: nx.MultiDiGraph, goal: GoalSpec) -> PlanSegment:
    if goal.step_template:
        steps = list(goal.step_template)
        if _uses_token(steps) and not _produces_token(steps):
            steps = auth_provisioning() + steps
        return PlanSegment(goal=goal.name, steps=steps)
    ep_index = {(ep.methods[0], ep.route): ep for ep in model.endpoints}
    drop = set(goal.drop_requires)
    agenda: list[tuple[str, int]] = [(goal.target, goal.max_depth)]
    seen_atoms = {goal.target}
    collected: list[str] = []
    soft_map: dict[str, str] = {}  
    notes: list[str] = []

    while agenda:
        atom, depth = agenda.pop(0)
        if depth <= 0:
            continue
        producers = [
            u for u, _, d in sstg.in_edges(atom, data=True) if d.get("kind") == "produces"
        ]
        if producers:
            
            action = _pick_producer(producers, sstg, seen_atoms, drop)
        else:
            soft = _soft_producers(model, atom)
            if not soft:
                notes.append(f"coverage-gap: {atom} 无生产者(analyzer 质量指标)")
                continue
            
            
            action = soft[0]
            soft_map[atom] = action
            notes.append(f"soft-producer: {atom} ← {action}(静态无 produces 边,运行时 verify 裁决)")
        if action not in collected:
            collected.append(action)
        for _, v, d in sstg.out_edges(action, data=True):
            if d.get("kind") != "requires" or v in seen_atoms:
                continue
            var = v.split("=", 1)[0]
            if var in drop:
                notes.append(f"drop-requires: {action} 的 {v} 前置按攻击假设跳过")
                continue
            seen_atoms.add(v)
            agenda.append((v, depth - 1))

    ordered = _topo_order(sstg, collected, soft_map)
    steps = [_to_step(ep_index, a, goal) for a in ordered]
    steps = _ensure_auth(steps)  
    steps = _resource_completion(model, ep_index, goal, steps, _to_step)
    return PlanSegment(goal=goal.name, steps=steps, notes=notes)


def _topo_order(sstg: nx.MultiDiGraph, actions: list[str],
                soft_map: dict[str, str]) -> list[str]:
    producers_of: dict[str, list[str]] = {}
    for a in actions:
        for _, v, d in sstg.out_edges(a, data=True):
            if d.get("kind") == "produces":
                producers_of.setdefault(v, []).append(a)
    for atom, a in soft_map.items():
        producers_of.setdefault(atom, []).append(a)

    deps: dict[str, set[str]] = {a: set() for a in actions}
    for a in actions:
        for _, v, d in sstg.out_edges(a, data=True):
            if d.get("kind") == "requires":
                for p in producers_of.get(v, []):
                    if p in deps and p != a:
                        deps[a].add(p)

    out: list[str] = []
    remaining = list(actions)
    while remaining:
        ready = [a for a in remaining if not (deps[a] & set(remaining))]
        if not ready:  
            ready = remaining[:1]
        for a in ready:
            out.append(a)
            remaining.remove(a)
    return out


def _soft_producers(model: AppModel, atom: str) -> list[str]:
    
    var = atom.split("=", 1)[0]
    attr = var.split(".")[1]
    candidates = []
    for ep in model.endpoints:
        if attr in ep.observes and ep.methods[0] in ("POST", "PUT"):
            candidates.append(f"{ep.methods[0]} {ep.route}")
    candidates.sort(key=lambda a: "<" not in a)  
    return candidates


def _to_step(ep_index: dict, action: str, goal: GoalSpec) -> PlanStep:
    
    method, _, route = action.partition(" ")
    ep = ep_index.get((method, route))
    step = PlanStep(action=action)
    if ep is None:
        return step
    for p in ep.params:
        if p.location == "path":
            step.path[p.name] = f"?{p.name}"
        elif p.location == "json":
            step.json[p.name] = goal.param_overrides.get(p.name) or _JSON_FILL.get(p.name, "x")
    if any(pre.var == "Session.authed_as" for pre in ep.preconditions):
        step.headers["Authorization"] = "Bearer ?token"
    if route.endswith("/login"):
        step.extract["token"] = "?token"
    elif method == "POST" and "<" not in route and ep.observes and "id" in ep.observes:
        step.extract["id"] = "?oid"
    return step
