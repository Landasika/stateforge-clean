from __future__ import annotations
import ast
from pathlib import Path

from stateforge.core.ir import ProgramIR
from stateforge.solving.branch_distance import BranchDistance, branch_distance
from stateforge.solving.branch_observer import BranchObservation
from stateforge.solving.input_provenance import (InputSource,
                                                     resolve_operand_source)
from stateforge.solving.stalled import StalledFrontier

M_DISTANCE_HISTORY = 10     


def _local_cfg(ir: ProgramIR, function: str) -> dict:
    
    blocks = [{"id": b.id, "kind": b.kind,
               "lines": [b.start_line, b.end_line]}
              for b in ir.blocks.values() if b.function == function]
    bids = {b["id"] for b in blocks}
    edges = [{"src": e.src, "dst": e.dst, "kind": e.kind}
             for e in ir.edges if e.src in bids and e.dst in bids]
    callers = sorted({e.src for e in ir.edges
                      if e.kind == "call" and e.dst in bids})
    return {"function": function, "blocks": blocks, "edges": edges,
            "callers": callers}


def _backward_flow(app_path: Path, function: str, guard_lineno: int) -> list[str]:
    
    try:
        tree = ast.parse(Path(app_path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == function), None)
    if fn is None:
        return []
    stmts = []
    for node in ast.walk(fn):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) \
                and node.lineno < guard_lineno:
            try:
                stmts.append((node.lineno, ast.unparse(node)))
            except Exception:                
                pass
    return [text for _, text in sorted(stmts)]


def _failed_mutations(frontier_id: str, corpus_meta: list[dict]) -> list[dict]:
    
    out = []
    for m in corpus_meta:
        if m.get("nearest_frontier") == frontier_id:
            out.append({"input_id": m["input_id"],
                        "target_value": m.get("distance"),
                        "reason": m.get("interesting_reason")})
    return out


def build_slice(ir: ProgramIR, stalled: StalledFrontier,
                observations: list[BranchObservation],
                provenance: InputSource,
                app_path: str | Path,
                corpus_meta: list[dict] | None = None) -> dict:
    u, v = stalled.edge
    guard = stalled.guard
    block = ir.blocks[u]

    
    relevant = [o for o in observations if o.guard_id == guard.guard_id]
    history = []
    for obs in relevant[-M_DISTANCE_HISTORY:]:
        d: BranchDistance = branch_distance(obs, guard.polarity)
        history.append({
            "lhs": repr(obs.lhs), "rhs": repr(obs.rhs),
            "actual": obs.actual,
            "distance_raw": d.raw_distance,
            "distance_norm": d.normalized_distance,
            "satisfied": d.satisfied})

    return {
        "target_frontier": {
            "edge": [u, v], "polarity": guard.polarity,
            "source_hit_count": stalled.source_hit_count},
        "guard": {
            "expression": guard.expression, "op": guard.op,
            "lineno": guard.lineno, "col_offset": guard.col_offset,
            "guard_id": guard.guard_id},
        "local_cfg": _local_cfg(ir, block.function),
        "backward_dataflow": _backward_flow(Path(app_path), block.function,
                                            guard.lineno),
        "input_source": {
            "kind": provenance.kind, "key": provenance.key,
            "transform_chain": list(provenance.transforms),
            "status": provenance.status},
        "runtime": {
            "observations_seen": len(relevant),
            "distance_history": history},
        "failed_mutations": _failed_mutations(stalled.frontier_id,
                                              corpus_meta or []),
    }
