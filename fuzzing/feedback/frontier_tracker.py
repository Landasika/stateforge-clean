from __future__ import annotations
from stateforge.core.ir import ProgramIR

_EXEC_KINDS = {"flow", "true", "false", "call", "return"}


class FrontierTracker:
    def __init__(self, ir: ProgramIR):
        self.ir = ir
        self._static_edges = [(e.src, e.dst) for e in ir.edges
                              if e.kind in _EXEC_KINDS]
        self.covered_blocks: set[str] = set()
        self.covered_edges: set[tuple[str, str]] = set()
        self.version: int = 0
        self.edge_frontiers: list[tuple[str, str]] = []
        self.node_frontiers: list[str] = []
        self._created: dict[tuple[str, str], float] = {}
        self.lifecycle_events: list[dict] = []      

    def update(self, blocks: set[str], edges: set[tuple[str, str]]) -> bool:
        
        grew = not (blocks <= self.covered_blocks and edges <= self.covered_edges)
        self.covered_blocks |= blocks
        self.covered_edges |= edges
        if grew:
            self._recompute()
            self.version += 1
        return grew

    def _recompute(self) -> None:
        import time
        now = time.time()
        prev = set(self.edge_frontiers)
        self.edge_frontiers = [
            (u, v) for (u, v) in self._static_edges
            if u in self.covered_blocks and (u, v) not in self.covered_edges]
        cur = set(self.edge_frontiers)
        for e in cur - prev:                        
            self._created.setdefault(e, now)
        for e in prev - cur:                        
            t0 = self._created.pop(e, None)
            if t0 is not None and e in self.covered_edges:
                self.lifecycle_events.append(
                    {"edge": list(e), "created": round(t0, 3),
                     "crossed": round(now, 3),
                     "crossing_seconds": round(now - t0, 3)})
        self.node_frontiers = sorted({v for (_, v) in self.edge_frontiers
                                      if v not in self.covered_blocks})

    def drain_lifecycle(self) -> list[dict]:
        out, self.lifecycle_events = self.lifecycle_events, []
        return out

    def state(self) -> dict:
        return {"covered_blocks": sorted(self.covered_blocks),
                "covered_edges": [list(e) for e in sorted(self.covered_edges)],
                "version": self.version,
                "edge_frontiers": [list(e) for e in self.edge_frontiers]}
