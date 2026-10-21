from __future__ import annotations
import ast
from dataclasses import dataclass, field
from pathlib import Path
from stateforge.state.observer import Abstractor, StateNode, StateRegistry
from stateforge.state.predicate_extractor import _resolve_condition
from stateforge.state.semantic_model import StateOp
from stateforge.state.session_access import analyze_session_access
from stateforge.state.state_provenance import SessionProvenance
@dataclass(frozen=True)
class TransitionEdge:
    

    from_key: str
    to_key: str
    trigger: str
    evidence: list[str] = field(default_factory=list)

    @property
    def dedup_key(self) -> tuple[str, str, str]:
        
        return (self.from_key, self.to_key, self.trigger)


def _trigger_label(request_id) -> str:
    return request_id if isinstance(request_id, str) else f"req-{request_id}"
class TransitionRecorder:

    def __init__(self, registry: StateRegistry, abstractor: Abstractor):
        self.registry = registry
        self.abstractor = abstractor
        self._current: StateNode | None = None
        self._tick = 0

    def new_session(self, initial: dict | None = None) -> None:
        self._current = None
        if initial is not None:
            self._current = self._register(initial)

    def observe(self, request_id, session: dict) -> StateNode:
        
        self._tick += 1
        node = self.registry.observe(self.abstractor.abstract(session),
                                     self._tick)
        prev, self._current = self._current, node
        if prev is not None and prev.state.canonical_key != node.state.canonical_key:
            self.registry.add_edge(TransitionEdge(
                from_key=prev.state.canonical_key,
                to_key=node.state.canonical_key,
                trigger=_trigger_label(request_id),
                evidence=["dynamic:state-diff"]))
        return node
    def _register(self, session: dict) -> StateNode:
        self._tick += 1
        return self.registry.observe(self.abstractor.abstract(session),
                                     self._tick)


@dataclass(frozen=True)
class StaticCandidate:
    
    function: str
    var: str
    op: str
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"function": self.function, "var": self.var,
                "op": self.op, "evidence": list(self.evidence)}


_MUTATION_OPS = frozenset({StateOp.SET, StateOp.UPDATE})


def static_transition_candidates(source_dir) -> list[StaticCandidate]:
    
    candidates: list[StaticCandidate] = []
    for access in analyze_session_access(source_dir):
        if access.operation in _MUTATION_OPS:
            candidates.append(StaticCandidate(
                function=access.function or "<module>",
                var=access.variable.canonical,
                op=access.operation.value,
                evidence=[f"{access.filename}:{access.lineno}"]))
    for py in sorted(Path(source_dir).rglob("*.py")):
        if "__pycache__" in str(py):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            candidates.extend(_guard_candidates(fn, str(py)))
    return candidates


def _guard_candidates(fn, filename: str) -> list[StaticCandidate]:
    
    prov = SessionProvenance()
    prov.analyze(fn)
    out: list[StaticCandidate] = []
    for node in ast.walk(fn):
        if not isinstance(node, (ast.If, ast.While)):
            continue
        pred = _resolve_condition(node.test, prov)
        if pred is None:
            continue
        op = f"guard:{pred.op.value}"
        if pred.value is not None:
            op = f"guard:{pred.op.value}({pred.value})"
        out.append(StaticCandidate(
            function=fn.name, var=pred.variable.canonical, op=op,
            evidence=[f"{filename}:{node.lineno}"]))
    return out
