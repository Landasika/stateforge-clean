from pathlib import Path

import pytest

from stateforge.analysis.static.icfg import _source_hash, build_icfg
from stateforge.core.ir import BasicBlock, ProgramIR
from stateforge.fuzzing.feedback.distance import target_distances
from stateforge.fuzzing.guidance.target import (
    BasicBlockTarget,
    InvalidTargetError,
    StaleIRError,
    TargetManager,
)
from stateforge.runtime.mapper import MappedTrace
from tests.helpers import build_example_ir, target_block_id

SOURCE = (
    "def stage():\n"
    "    return 1\n"
    "def target(data):\n"
    "    if len(data) < 2:\n"
    "        return None\n"
    "    if data[0] == 65:\n"
    "        stage()\n"
    "        if data[1] == 66:\n"
    "            return stage()\n"
    "    return None\n"
)


def test_valid_target_and_self_distance():
    ir = build_example_ir()
    block_id = target_block_id(ir)
    manager = TargetManager(ir, BasicBlockTarget(block_id))
    assert manager.distance(block_id) == 0
    assert manager.distance_for_trace(MappedTrace(blocks=[block_id])) == 0
    assert manager.reached(MappedTrace(blocks=[block_id]))
    assert not manager.reached(MappedTrace(blocks=[]))


def test_invalid_target_is_rejected():
    ir = build_example_ir()
    with pytest.raises(InvalidTargetError):
        TargetManager(ir, BasicBlockTarget("missing-block"))


def test_shortest_path_matches_existing_distance_function():
    ir = build_example_ir()
    block_id = target_block_id(ir)
    manager = TargetManager(ir, BasicBlockTarget(block_id))
    expected = target_distances(ir, {block_id})
    for source in expected:
        assert manager.distance(source) == expected[source]
    incoming = ir.incoming(block_id)
    assert incoming
    assert manager.distance(incoming[0].src) == 1


def test_unreachable_block_is_unknown_not_zero():
    ir = build_example_ir()
    block_id = target_block_id(ir)
    ir.blocks["orphan"] = BasicBlock(
        "orphan", str(Path("orphan.py")), "orphan", "f", 1, 1)
    manager = TargetManager(ir, BasicBlockTarget(block_id))
    assert manager.distance("orphan") is None
    assert manager.distance_for_trace(MappedTrace(blocks=["orphan"])) is None
    assert not manager.reached(MappedTrace(blocks=["orphan"]))


def test_empty_trace_has_unknown_distance():
    ir = build_example_ir()
    manager = TargetManager(ir, BasicBlockTarget(target_block_id(ir)))
    assert manager.distance_for_trace(MappedTrace()) is None


def test_distance_lookup_is_read_only():
    ir = build_example_ir()
    block_id = target_block_id(ir)
    manager = TargetManager(ir, BasicBlockTarget(block_id))
    with pytest.raises(TypeError):
        manager.distances[block_id] = 10


def test_stale_source_hash_is_rejected_and_override_is_explicit(tmp_path: Path):
    source = tmp_path / "app.py"
    source.write_text(SOURCE, encoding="utf-8")
    ir = build_icfg(tmp_path)
    block_id = ir.functions["app.target"].entry
    TargetManager(ir, BasicBlockTarget(block_id))
    ir.metadata["source_hash"] = "0" * 64
    with pytest.raises(StaleIRError):
        TargetManager(ir, BasicBlockTarget(block_id))
    manager = TargetManager(ir, BasicBlockTarget(block_id), allow_stale=True)
    assert manager.stale
    assert manager.distance(block_id) == 0


def test_fresh_source_hash_is_accepted(tmp_path: Path):
    source = tmp_path / "app.py"
    source.write_text(SOURCE, encoding="utf-8")
    ir = build_icfg(tmp_path)
    assert ir.metadata["source_hash"] == _source_hash(tmp_path)
    manager = TargetManager(ir, BasicBlockTarget(ir.functions["app.target"].entry))
    assert not manager.stale


def test_missing_source_metadata_skips_freshness_validation():
    ir = ProgramIR()
    ir.blocks["bb"] = BasicBlock("bb", "/x.py", "m", "f", 1, 1)
    manager = TargetManager(ir, BasicBlockTarget("bb"))
    assert manager.distance("bb") == 0
    assert not manager.stale
