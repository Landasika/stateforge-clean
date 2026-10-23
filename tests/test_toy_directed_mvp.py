import json
from pathlib import Path

from stateforge.analysis.static.icfg import build_icfg
from stateforge.fuzzing.feedback.corpus import GuidedCorpus
from stateforge.fuzzing.guidance.campaign import (
    CampaignConfig,
    ExecutionResult,
    GuidedCampaign,
)
from stateforge.fuzzing.guidance.mutator import BasicMutator
from stateforge.fuzzing.guidance.scheduler import GuidedScheduler
from stateforge.fuzzing.guidance.target import BasicBlockTarget, TargetManager
from targets.toy_app.adapter import build_adapter

ROOT = Path(__file__).resolve().parents[1]
TARGET_ROOT = ROOT / "targets" / "toy_app" / "target"
SEEDS = ROOT / "targets" / "toy_app" / "seeds"


def _ir():
    return build_icfg(TARGET_ROOT)


def _target_id(ir) -> str:
    return next(
        block_id for block_id, block in ir.blocks.items()
        if block.function == "deep_target"
        and any("TARGET_REACHED" in statement
                for statement in block.statements))


def _campaign(ir, output=None, max_executions=100):
    target_id = _target_id(ir)
    return GuidedCampaign(
        ir=ir,
        target=BasicBlockTarget(target_id),
        adapter=build_adapter(),
        corpus=GuidedCorpus(100),
        scheduler=GuidedScheduler(epsilon=0.2, random_seed=42,
                                 min_energy=1, max_energy=1),
        mutator=BasicMutator(42),
        config=CampaignConfig(
            max_executions=max_executions,
            max_corpus_size=100,
            epsilon=0.2,
            random_seed=42,
            min_energy=1,
            max_energy=1,
            output_dir=output,
        ),
    )


def test_toy_target_distance_progression_and_mapping_diagnostics():
    ir = _ir()
    campaign = _campaign(ir)
    expected = [
        (b"\x00\x00", 2, False),
        (b"\x32\x00", 1, False),
        (b"\x32\x96", 0, True),
    ]
    for data, distance, reached in expected:
        result = campaign.execute_input(data)
        assert result.distance == distance
        assert result.target_reached is reached
        assert result.unresolved_events == 0
        assert result.unmatched_edge_count == 0
        assert result.valid_edge_count > 0
        assert result.nearest_block is not None
    assert campaign.session.events == []


def test_target_manager_distinguishes_proximity_from_hit():
    ir = _ir()
    target_id = _target_id(ir)
    manager = TargetManager(ir, BasicBlockTarget(target_id))
    campaign = _campaign(ir)
    near = campaign.execute_input(b"\x32\x00")
    assert near.distance == 1
    assert near.nearest_block != target_id
    assert not near.target_reached
    hit = campaign.execute_input(b"\x32\x96")
    assert hit.distance == 0
    assert hit.nearest_block == target_id
    assert hit.target_reached


def test_directed_campaign_reaches_toy_target_and_replays(tmp_path: Path):
    out = tmp_path / "out"
    ir = _ir()
    campaign = _campaign(ir, output=out, max_executions=100)
    seeds = [
        (SEEDS / "seed_00.bin").read_bytes(),
        (SEEDS / "seed_01.bin").read_bytes(),
    ]
    result = campaign.run(seeds)
    assert result.target_reached
    assert result.termination_reason == "target_reached"
    assert result.best_distance == 0
    assert result.mapping_failures == 0
    reproducer = (out / "target_reaching_input.bin").read_bytes()
    assert len(reproducer) >= 2
    assert reproducer[0] > 20
    assert reproducer[1] > 100
    replay_ir = _ir()
    replay = _campaign(replay_ir)
    replayed = replay.execute_input(reproducer)
    assert replayed.target_reached
    assert replayed.distance == 0
    records = [
        json.loads(line)
        for line in (out / "metrics.jsonl").read_text().splitlines()
    ]
    assert records[-1]["target_reached"] is True
    assert records[-1]["distance_improved"] is True
    assert records[-1]["nearest_block"] == _target_id(ir)
    assert any(record["distance_improved"] for record in records)


def _result(blocks, distance):
    return ExecutionResult(
        input_id="x",
        parent_id=None,
        covered_blocks=frozenset(blocks),
        covered_edges=frozenset(),
        distance=distance,
        target_reached=False,
        execution_time_ms=0.0,
        error=None,
    )


def test_coverage_only_corpus_ignores_distance_only_progress():
    coverage = GuidedCorpus(10, retention_policy="coverage")
    assert coverage.consider(b"a", _result({"a"}, 5))
    assert not coverage.consider(b"b", _result({"a"}, 1))
    assert coverage.best_distance == 1
    assert coverage.consider(b"c", _result({"b"}, 5))

    distance = GuidedCorpus(10, retention_policy="distance")
    assert distance.consider(b"a", _result({"a"}, 5))
    assert distance.consider(b"b", _result({"a"}, 1))


def test_campaign_config_controls_corpus_policy():
    ir = _ir()
    config = CampaignConfig(max_executions=1, corpus_policy="coverage")
    campaign = GuidedCampaign(
        ir=ir,
        target=BasicBlockTarget(_target_id(ir)),
        adapter=build_adapter(),
        config=config,
    )
    assert campaign.corpus.retention_policy == "coverage"


NESTED_ROOT = ROOT / "targets" / "toy_nested" / "target"
NESTED_SEEDS = ROOT / "targets" / "toy_nested" / "seeds"


def test_interprocedural_toy_target_distance_progression():
    from targets.toy_nested.adapter import build_adapter as nested_adapter

    ir = build_icfg(NESTED_ROOT)
    target_id = next(
        block_id for block_id, block in ir.blocks.items()
        if any("TARGET_REACHED" in statement
               for statement in block.statements))
    campaign = GuidedCampaign(
        ir=ir,
        target=BasicBlockTarget(target_id),
        adapter=nested_adapter(),
        corpus=GuidedCorpus(20),
        scheduler=GuidedScheduler(epsilon=0.0, random_seed=0),
        mutator=BasicMutator(random_seed=0),
        config=CampaignConfig(max_executions=10),
    )
    expected = [
        (bytes([0, 0, 0, 0]), 7, False),
        (bytes([50, 0, 0, 0]), 6, False),
        (bytes([50, 150, 0, 0]), 2, False),
        (bytes([50, 150, 200, 0]), 1, False),
        (bytes([50, 150, 200, 250]), 0, True),
    ]
    for data, distance, reached in expected:
        result = campaign.execute_input(data)
        assert result.distance == distance
        assert result.target_reached is reached
        assert result.unmatched_edge_count == 0
        assert result.unresolved_events == 0
    replay = campaign.execute_input(
        (ROOT / "targets" / "toy_nested" / "replay" / "target.bin").read_bytes())
    assert replay.target_reached
    assert replay.distance == 0
