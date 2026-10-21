import pytest

from stateforge.fuzzing.feedback.distance import target_distances
from stateforge.fuzzing.feedback.scorer import (
    score_distance,
    score_trace,
    score_trace_cached,
    trace_distance,
)
from stateforge.runtime.mapper import MappedTrace
from tests.helpers import build_example_ir, target_block_id


def _trace(blocks):
    return MappedTrace(blocks=list(blocks))


def test_score_increases_as_distance_decreases():
    assert score_distance(None) == 0.0
    assert score_distance(0) == 1.0
    assert score_distance(1) > score_distance(2) > score_distance(10) > 0.0


def test_cached_trace_score_and_distance():
    ir = build_example_ir()
    block_id = target_block_id(ir)
    distances = target_distances(ir, {block_id})
    assert score_trace_cached(_trace([block_id]), distances) == 1.0
    assert score_trace_cached(_trace([]), distances) == 0.0
    assert score_trace_cached(_trace(["unknown"]), distances) == 0.0
    assert trace_distance(_trace(["unknown"]), distances) is None


def test_cached_and_direct_scores_match():
    ir = build_example_ir()
    block_id = target_block_id(ir)
    distances = target_distances(ir, {block_id})
    trace = _trace([ir.functions["m1_target.stage_two"].entry])
    assert score_trace(ir, trace, {block_id}) == score_trace_cached(trace, distances)


def test_precomputed_distances_are_reused(monkeypatch):
    ir = build_example_ir()
    block_id = target_block_id(ir)
    distances = target_distances(ir, {block_id})
    trace = _trace([block_id])

    def explode(*args, **kwargs):
        raise AssertionError("distance recomputation attempted")

    monkeypatch.setattr(
        "stateforge.fuzzing.feedback.scorer.distance_to_targets", explode)
    assert score_trace(ir, trace, {block_id}, distances) == 1.0
    assert score_trace_cached(trace, distances) == 1.0


def test_unreachable_and_empty_traces_do_not_reward():
    ir = build_example_ir()
    block_id = target_block_id(ir)
    distances = target_distances(ir, {block_id})
    assert score_trace_cached(_trace([]), distances) == 0.0
    assert score_trace_cached(_trace(["orphan"]), distances) == 0.0
    assert score_trace_cached(_trace(["orphan"]), {}) == 0.0
    assert score_trace(ir, _trace([]), {block_id}) == 0.0


def test_target_hit_forces_full_reward():
    ir = build_example_ir()
    block_id = target_block_id(ir)
    distances = target_distances(ir, {block_id})
    assert trace_distance(_trace([block_id]), distances) == 0
    assert score_trace_cached(_trace([block_id]), distances) == pytest.approx(1.0)
