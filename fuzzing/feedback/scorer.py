
from __future__ import annotations

from collections.abc import Mapping

from stateforge.core.ir import ProgramIR
from stateforge.runtime.mapper import MappedTrace
from stateforge.fuzzing.feedback.distance import distance_to_targets


def trace_distance(trace: MappedTrace, distances: Mapping[str, int]) -> int | None:
    known = [distances[block] for block in trace.blocks if block in distances]
    return min(known) if known else None


def score_distance(distance: int | None) -> float:
    if distance is None:
        return 0.0
    return 1.0 / (1.0 + distance)


def score_trace_cached(trace: MappedTrace, distances: Mapping[str, int]) -> float:
    if not trace.blocks or not distances:
        return 0.0
    return score_distance(trace_distance(trace, distances))


def score_trace(ir: ProgramIR, trace: MappedTrace, targets: set[str],
                distances: Mapping[str, int] | None = None) -> float:
    if not targets or not trace.blocks:
        return 0.0
    if distances is None:
        distances = distance_to_targets(ir, set(trace.blocks), targets)
    return score_trace_cached(trace, distances)


def score_frontier(ir: ProgramIR, src: str, dst: str) -> float:
    distances = distance_to_targets(ir, {src}, {dst})
    return 1.0 / (1.0 + distances.get(src, 10**9))
