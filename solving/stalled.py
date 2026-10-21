from __future__ import annotations
from dataclasses import dataclass

from stateforge.core.ir import ProgramIR
from stateforge.solving.guard_ir import BranchGuard
from stateforge.solving.guard_recovery import _TestIndex, recover_guard

N_MIN_HITS = 100            


@dataclass(frozen=True)
class StalledFrontier:
    edge: tuple[str, str]
    source_hit_count: int
    guard: BranchGuard

    @property
    def frontier_id(self) -> str:
        return f"{self.edge[0]}->{self.edge[1]}"


def find_stalled(ir: ProgramIR, covered_blocks: dict[str, int],
                 covered_edges: set[tuple[str, str]],
                 test_index: _TestIndex | None = None,
                 min_hits: int = N_MIN_HITS
                 ) -> list[StalledFrontier]:
    
    idx = test_index or _TestIndex(ir)
    out: list[StalledFrontier] = []
    for e in ir.edges:
        if e.kind not in ("true", "false"):
            continue
        u, v = e.src, e.dst
        hits = covered_blocks.get(u, 0)
        if hits < min_hits or (u, v) in covered_edges:
            continue
        guard = recover_guard(ir, u, v, e.kind, idx)
        if guard.status != "ok":
            continue
        out.append(StalledFrontier((u, v), hits, guard))
    out.sort(key=lambda sf: -sf.source_hit_count)
    return out
