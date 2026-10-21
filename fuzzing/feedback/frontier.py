
from __future__ import annotations

from dataclasses import dataclass

from stateforge.core.ir import FlowEdge, ProgramIR
from stateforge.fuzzing.feedback.overlay import Overlay


@dataclass(frozen=True)
class Frontier:
    src: str
    dst: str
    kind: str
    distance: int | None = None


@dataclass(frozen=True)
class EdgeFrontier:
    src: str
    dst: str
    kind: str


def find_frontiers(ir: ProgramIR, overlay: Overlay) -> list[Frontier]:
    return [Frontier(e.src, e.dst, e.kind)
            for e in ir.edges
            if e.kind in {"flow", "true", "false", "call", "return"}
            and e.src in overlay.covered_blocks and e.dst not in overlay.covered_blocks]


def find_edge_frontiers(ir: ProgramIR, overlay: Overlay) -> list[EdgeFrontier]:
    return [EdgeFrontier(e.src, e.dst, e.kind)
            for e in ir.edges
            if e.kind in {"flow", "true", "false", "call", "return"}
            and e.src in overlay.covered_blocks
            and (e.src, e.dst) not in overlay.covered_edges]
