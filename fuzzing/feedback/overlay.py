
from __future__ import annotations

from dataclasses import dataclass

from stateforge.core.ir import ProgramIR
from stateforge.runtime.mapper import MappedTrace


@dataclass
class Overlay:
    covered_blocks: set[str]
    covered_edges: set[tuple[str, str]]
    block_hits: dict[str, int]
    edge_hits: dict[tuple[str, str], int]
    block_request_count: dict[str, int]
    edge_request_count: dict[tuple[str, str], int]


def build_overlay(ir: ProgramIR, trace: MappedTrace) -> Overlay:
    valid_edges = set(trace.observed_valid_edges)
    if not valid_edges and not trace.observed_valid_edges:
        valid_edges = set(trace.edge_kinds)
    return Overlay(
        set(trace.block_hits), valid_edges,
        dict(trace.block_hits),
        {edge: count for edge, count in trace.edge_hits.items()
         if edge in valid_edges},
        {b: len(r) for b, r in trace.block_requests.items()},
        {e: len(r) for e, r in trace.edge_requests.items()
         if e in valid_edges})
