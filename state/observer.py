from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from stateforge.state.semantic_model import AbstractValue, AbstractState
from stateforge.state.domain_builder import VarDomain, build_domains

if TYPE_CHECKING:  
    from stateforge.state.transition import TransitionEdge


class Abstractor:
    

    def __init__(self, domains: dict[str, VarDomain]):
        self.domains = domains
    def abstract(self, session: dict) -> AbstractState:
        values = []
        for key, domain in self.domains.items():
            short_key = domain.variable.key
            concrete = session.get(short_key)
            name = domain.abstract(concrete)
            values.append(AbstractValue(domain.variable, name))
        return AbstractState(tuple(sorted(values, key=lambda v: v.variable.canonical)))


@dataclass
class StateNode:
    id: str
    state: AbstractState
    hit_count: int = 0
    first_seen: int = -1


class StateRegistry:
    

    def __init__(self):
        self._states: dict[str, StateNode] = {}
        self._seq = 0
        self._edges: dict[tuple[str, str, str], TransitionEdge] = {}
    def observe(self, state: AbstractState, request_id: int = 0) -> StateNode:
        key = state.canonical_key
        if key not in self._states:
            self._states[key] = StateNode(
                id=f"S{self._seq}", state=state,
                first_seen=request_id)
            self._seq += 1
        node = self._states[key]
        node.hit_count += 1
        return node

    def add_edge(self, edge: TransitionEdge) -> bool:
        
        if edge.dedup_key in self._edges:
            return False
        self._edges[edge.dedup_key] = edge
        return True

    @property
    def nodes(self) -> dict[str, StateNode]:
        return dict(self._states)

    @property
    def edges(self) -> dict[tuple[str, str, str], TransitionEdge]:
        return dict(self._edges)

    def summary(self) -> list[dict]:
        return [{"id": n.id, "state": n.state.to_dict(),
                 "hits": n.hit_count}
                for n in self._states.values()]

    def edge_summary(self) -> list[dict]:
        
        id_by_key = {n.state.canonical_key: n.id
                     for n in self._states.values()}
        return [{"from": id_by_key.get(e.from_key, e.from_key),
                 "to": id_by_key.get(e.to_key, e.to_key),
                 "trigger": e.trigger, "evidence": list(e.evidence)}
                for e in self._edges.values()]


def run_state_analysis(source_dir: str | Path) -> dict:
    from pathlib import Path
    from stateforge.state.session_access import analyze_session_access
    from stateforge.state.predicate_extractor import extract_predicates
    from stateforge.state.transition import static_transition_candidates

    accesses = analyze_session_access(source_dir)
    predicates = extract_predicates(source_dir)
    domains = build_domains(predicates)

    return {
        "accesses": [{"var": a.variable.canonical, "op": a.operation.value,
                       "fn": a.function, "file": a.filename, "line": a.lineno}
                      for a in accesses],
        "predicates": [p.to_dict() for p in predicates],
        "domains": {k: v.to_dict() for k, v in domains.items()},
        "n_variables": len(domains),
        "n_predicates": len(predicates),
        "transitions": {
            "static_candidates": [c.to_dict()
                                  for c in static_transition_candidates(source_dir)],
            "note": "dynamic edges are discovered at fuzz time by "
                    "TransitionRecorder.observe() into StateRegistry.edges",
        },
    }
