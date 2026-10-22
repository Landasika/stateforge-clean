
from pathlib import Path

from stateforge.analysis.static.icfg import build_icfg
from stateforge.adapters.callable import CallableAdapter
from stateforge.core.ir import BasicBlock, FlowEdge, ProgramIR
from stateforge.fuzzing.feedback.distance import target_distances
from stateforge.fuzzing.feedback.scorer import score_trace
from stateforge.fuzzing.guidance.deviation import (
    DeviationAnalyzer,
    DeviationPoint,
    find_deviation_points,
)
from stateforge.runtime.mapper import MappedTrace, map_trace
from stateforge.runtime.tracer import TraceSession
from examples.m1_target import target
from tests.helpers import build_example_ir, target_block_id


def _block(block_id: str, kind: str = "block") -> BasicBlock:
    return BasicBlock(block_id, "app.py", "app", "f", 1, 1, kind)


def _diamond() -> ProgramIR:
    ir = ProgramIR()
    for block_id in ("entry", "branch", "near", "far", "target"):
        ir.blocks[block_id] = _block(
            block_id, "branch" if block_id == "branch" else "block")
    ir.add_edge(FlowEdge("entry", "branch", "flow"))
    ir.add_edge(FlowEdge("branch", "near", "true"))
    ir.add_edge(FlowEdge("branch", "far", "false"))
    ir.add_edge(FlowEdge("near", "target", "flow"))
    return ir


def _trace(blocks, edges, kinds, unresolved=()):
    return MappedTrace(
        blocks=list(blocks),
        edges=list(edges),
        edge_kinds={edge: set(kind) for edge, kind in kinds.items()},
        unresolved=list(unresolved),
    )


def test_detects_branch_leading_away_from_target():
    ir = _diamond()
    trace = _trace(
        ["entry", "branch", "far"],
        [("entry", "branch"), ("branch", "far")],
        {("entry", "branch"): {"flow"}, ("branch", "far"): {"false"}},
    )
    points = find_deviation_points(ir, "target", trace)
    assert len(points) == 1
    point = points[0]
    assert point.block_id == "branch"
    assert point.observed_successor == "far"
    assert point.desired_successor == "near"
    assert point.observed_distance is None
    assert point.desired_distance == 1
    assert 0.0 < point.confidence <= 1.0


def test_no_deviation_when_observed_successor_is_preferred():
    ir = _diamond()
    trace = _trace(
        ["entry", "branch", "near", "target"],
        [("entry", "branch"), ("branch", "near"), ("near", "target")],
        {("entry", "branch"): {"flow"}, ("branch", "near"): {"true"},
         ("near", "target"): {"flow"}},
    )
    assert find_deviation_points(ir, "target", trace) == []


def test_multiple_successors_selects_nearest_finite_alternative():
    ir = ProgramIR()
    for block_id in ("entry", "branch", "a", "b", "c", "target"):
        ir.blocks[block_id] = _block(
            block_id, "branch" if block_id == "branch" else "block")
    ir.add_edge(FlowEdge("entry", "branch", "flow"))
    ir.add_edge(FlowEdge("branch", "a", "true"))
    ir.add_edge(FlowEdge("branch", "b", "false"))
    ir.add_edge(FlowEdge("branch", "c", "false"))
    ir.add_edge(FlowEdge("a", "b", "flow"))
    ir.add_edge(FlowEdge("b", "target", "flow"))
    trace = _trace(
        ["entry", "branch", "a"],
        [("entry", "branch"), ("branch", "a")],
        {("entry", "branch"): {"flow"}, ("branch", "a"): {"true"}},
    )
    points = find_deviation_points(ir, "target", trace)
    assert len(points) == 1
    assert points[0].observed_successor == "a"
    assert points[0].desired_successor == "b"
    assert points[0].desired_distance < points[0].observed_distance


def test_equal_distance_successors_do_not_create_false_deviation():
    ir = ProgramIR()
    for block_id in ("entry", "branch", "a", "b", "target"):
        ir.blocks[block_id] = _block(
            block_id, "branch" if block_id == "branch" else "block")
    ir.add_edge(FlowEdge("entry", "branch", "flow"))
    ir.add_edge(FlowEdge("branch", "a", "true"))
    ir.add_edge(FlowEdge("branch", "b", "false"))
    ir.add_edge(FlowEdge("a", "target", "flow"))
    ir.add_edge(FlowEdge("b", "target", "flow"))
    trace = _trace(
        ["entry", "branch", "a", "target"],
        [("entry", "branch"), ("branch", "a"), ("a", "target")],
        {("entry", "branch"): {"flow"}, ("branch", "a"): {"true"},
         ("a", "target"): {"flow"}},
    )
    assert find_deviation_points(ir, "target", trace) == []


def test_tied_alternative_successors_are_ambiguous():
    ir = ProgramIR()
    for block_id in ("entry", "branch", "a", "b", "c", "target"):
        ir.blocks[block_id] = _block(
            block_id, "branch" if block_id == "branch" else "block")
    ir.add_edge(FlowEdge("entry", "branch", "flow"))
    ir.add_edge(FlowEdge("branch", "c", "true"))
    ir.add_edge(FlowEdge("branch", "a", "false"))
    ir.add_edge(FlowEdge("branch", "b", "false"))
    ir.add_edge(FlowEdge("a", "target", "flow"))
    ir.add_edge(FlowEdge("b", "target", "flow"))
    trace = _trace(
        ["entry", "branch", "c"],
        [("entry", "branch"), ("branch", "c")],
        {("entry", "branch"): {"flow"}, ("branch", "c"): {"true"}},
    )
    assert find_deviation_points(ir, "target", trace) == []


def test_loop_branch_is_deduplicated_and_keeps_observed_direction():
    ir = ProgramIR()
    for block_id in ("entry", "branch", "body", "target"):
        ir.blocks[block_id] = _block(
            block_id, "branch" if block_id == "branch" else "block")
    ir.add_edge(FlowEdge("entry", "branch", "flow"))
    ir.add_edge(FlowEdge("branch", "body", "true"))
    ir.add_edge(FlowEdge("branch", "target", "false"))
    ir.add_edge(FlowEdge("body", "branch", "flow"))
    trace = _trace(
        ["entry", "branch", "body", "branch", "body", "branch", "target"],
        [("entry", "branch"), ("branch", "body"), ("body", "branch"),
         ("branch", "body"), ("body", "branch"), ("branch", "target")],
        {("entry", "branch"): {"flow"}, ("branch", "body"): {"true"},
         ("body", "branch"): {"flow"}, ("branch", "target"): {"false"}},
    )
    points = find_deviation_points(ir, "target", trace)
    assert len(points) == 1
    assert points[0].block_id == "branch"
    assert points[0].observed_successor == "body"
    assert points[0].desired_successor == "target"


def test_unreachable_alternative_is_ignored():
    ir = ProgramIR()
    for block_id in ("entry", "branch", "near", "orphan", "target"):
        ir.blocks[block_id] = _block(
            block_id, "branch" if block_id == "branch" else "block")
    ir.add_edge(FlowEdge("entry", "branch", "flow"))
    ir.add_edge(FlowEdge("branch", "near", "true"))
    ir.add_edge(FlowEdge("branch", "orphan", "false"))
    ir.add_edge(FlowEdge("near", "target", "flow"))
    trace = _trace(
        ["entry", "branch", "orphan"],
        [("entry", "branch"), ("branch", "orphan")],
        {("entry", "branch"): {"flow"}, ("branch", "orphan"): {"false"}},
    )
    points = find_deviation_points(ir, "target", trace)
    assert len(points) == 1
    assert points[0].desired_successor == "near"
    assert points[0].observed_distance is None
    preferred = _trace(
        ["entry", "branch", "near", "target"],
        [("entry", "branch"), ("branch", "near"), ("near", "target")],
        {("entry", "branch"): {"flow"}, ("branch", "near"): {"true"},
         ("near", "target"): {"flow"}},
    )
    assert find_deviation_points(ir, "target", preferred) == []


def test_missing_branch_kind_is_treated_as_unknown():
    ir = _diamond()
    trace = _trace(
        ["entry", "branch", "far"],
        [("entry", "branch"), ("branch", "far")],
        {("entry", "branch"): {"flow"}},
    )
    assert find_deviation_points(ir, "target", trace) == []


def test_ambiguous_branch_kinds_are_treated_as_unknown():
    ir = _diamond()
    trace = _trace(
        ["entry", "branch", "far"],
        [("entry", "branch"), ("branch", "far")],
        {("entry", "branch"): {"flow"}, ("branch", "far"): {"true", "false"}},
    )
    assert find_deviation_points(ir, "target", trace) == []


def test_non_successor_transition_is_not_a_deviation():
    ir = _diamond()
    trace = _trace(
        ["entry", "branch", "unknown"],
        [("entry", "branch"), ("branch", "unknown")],
        {("entry", "branch"): {"flow"}, ("branch", "unknown"): {"false"}},
    )
    assert find_deviation_points(ir, "target", trace) == []


def test_branch_without_observed_transition_is_unknown():
    ir = _diamond()
    trace = _trace(["entry", "branch"], [("entry", "branch")],
                   {("entry", "branch"): {"flow"}})
    assert find_deviation_points(ir, "target", trace) == []


def test_unresolved_trace_lowers_confidence():
    ir = _diamond()
    clean = _trace(
        ["entry", "branch", "far"],
        [("entry", "branch"), ("branch", "far")],
        {("entry", "branch"): {"flow"}, ("branch", "far"): {"false"}},
    )
    noisy = _trace(
        ["entry", "branch", "far"],
        [("entry", "branch"), ("branch", "far")],
        {("entry", "branch"): {"flow"}, ("branch", "far"): {"false"}},
        unresolved=[object()],
    )
    clean_point = find_deviation_points(ir, "target", clean)[0]
    noisy_point = find_deviation_points(ir, "target", noisy)[0]
    assert noisy_point.confidence < clean_point.confidence


def test_analyzer_does_not_change_m1_trace_score():
    ir = _diamond()
    trace = _trace(
        ["entry", "branch", "far"],
        [("entry", "branch"), ("branch", "far")],
        {("entry", "branch"): {"flow"}, ("branch", "far"): {"false"}},
    )
    before = score_trace(ir, trace, {"target"})
    find_deviation_points(ir, "target", trace)
    after = score_trace(ir, trace, {"target"})
    assert before == after


def test_mapped_execution_yields_target_relevant_deviation():
    ir = build_example_ir()
    target_id = target_block_id(ir)
    branch_id = next(
        block_id for block_id, block in ir.blocks.items()
        if block.function == "target"
        and any("data[0] == 65" in statement
                for statement in block.statements))
    true_successor = next(
        edge.dst for edge in ir.outgoing(branch_id) if edge.kind == "true")
    session = TraceSession(Path(__file__).resolve().parents[1] / "examples")
    with session.trace_execution():
        with session.request() as rid:
            CallableAdapter(target).execute(b"ZZZ")
    events = session.drain_request_events(rid)
    mapped = map_trace(events, ir)
    distances = target_distances(ir, {target_id})
    points = find_deviation_points(ir, target_id, mapped, distances)
    assert any(point.block_id == branch_id
               and point.observed_successor != true_successor
               and point.desired_successor == true_successor
               for point in points)
    assert all(isinstance(point, DeviationPoint) for point in points)
    assert session.events == []


def test_points_are_ordered_by_relevance():
    ir = ProgramIR()
    for block_id in ("entry", "b1", "far1", "x", "b2", "y",
                     "far2", "target"):
        ir.blocks[block_id] = _block(
            block_id, "branch" if block_id.startswith("b") else "block")
    ir.add_edge(FlowEdge("entry", "b1", "flow"))
    ir.add_edge(FlowEdge("b1", "x", "true"))
    ir.add_edge(FlowEdge("b1", "far1", "false"))
    ir.add_edge(FlowEdge("x", "b2", "flow"))
    ir.add_edge(FlowEdge("b2", "y", "true"))
    ir.add_edge(FlowEdge("b2", "far2", "false"))
    ir.add_edge(FlowEdge("y", "target", "flow"))
    trace = _trace(
        ["entry", "b1", "far1", "b2", "far2"],
        [("entry", "b1"), ("b1", "far1"), ("far1", "b2"), ("b2", "far2")],
        {("entry", "b1"): {"flow"}, ("b1", "far1"): {"false"},
         ("far1", "b2"): {"flow"}, ("b2", "far2"): {"false"}},
    )
    points = find_deviation_points(ir, "target", trace)
    assert [point.block_id for point in points] == ["b2", "b1"]
    assert [point.desired_distance for point in points] == [1, 3]
