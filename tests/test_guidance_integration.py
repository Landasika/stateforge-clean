import json
from pathlib import Path
import sys

from stateforge.analysis.static.icfg import build_icfg
from stateforge.core.ir import BasicBlock
from stateforge.fuzzing.feedback.corpus import GuidedCorpus, seed_id_for
from stateforge.fuzzing.guidance.campaign import (
    CampaignConfig,
    GuidedCampaign,
)
from stateforge.fuzzing.guidance.mutator import BasicMutator
from stateforge.fuzzing.guidance.scheduler import (
    GuidedScheduler,
    UniformScheduler,
)
from stateforge.fuzzing.guidance.target import BasicBlockTarget, TargetManager
from stateforge.runtime.mapper import map_trace
from stateforge.runtime.tracer import TraceEvent
from stateforge.cli import main
from tests.helpers import (
    EXAMPLES,
    build_example_ir,
    example_adapter,
    example_seeds,
    target_block_id,
)
from tests.test_guidance_campaign import RecordingScheduler, StagedMutator


def _make_campaign(ir, scheduler=None, mutator=None, output=None,
                   max_executions=20):
    target_id = target_block_id(ir)
    config = CampaignConfig(
        max_executions=max_executions,
        random_seed=42,
        epsilon=0.2,
        output_dir=output,
        max_corpus_size=100,
        progress_every=10,
    )
    return GuidedCampaign(
        ir=ir,
        target=BasicBlockTarget(target_id),
        adapter=example_adapter(),
        corpus=GuidedCorpus(100),
        scheduler=scheduler or GuidedScheduler(epsilon=0.2, random_seed=42),
        mutator=mutator or StagedMutator(),
        config=config,
    )


def test_static_and_dynamic_feedback_pipeline():
    ir = build_example_ir()
    target_id = target_block_id(ir)
    manager = TargetManager(ir, BasicBlockTarget(target_id))
    campaign = _make_campaign(ir, max_executions=20)
    distances = []
    for data in (b"", b"A00", b"AB0", b"ABC"):
        result = campaign.execute_input(data)
        distances.append(result.distance)
        assert result.error is None
    assert distances == [18, 10, 3, 0]
    assert manager.distance(target_id) == 0
    assert campaign.target_manager.distance_for_trace(
        map_trace([], ir)) is None


def test_guided_and_uniform_baselines_both_reach_target(tmp_path: Path):
    guided_ir = build_example_ir()
    guided_scheduler = RecordingScheduler(epsilon=0.0, random_seed=42)
    guided = _make_campaign(
        guided_ir, scheduler=guided_scheduler, output=tmp_path / "guided")
    guided_result = guided.run([b"", b"A00", b"AB0"])
    assert guided_result.target_reached
    assert guided_result.termination_reason == "target_reached"
    assert seed_id_for(b"AB0") in guided_scheduler.selected

    uniform_ir = build_example_ir()
    uniform = _make_campaign(
        uniform_ir,
        scheduler=UniformScheduler(random_seed=42, energy=1),
        output=tmp_path / "uniform",
    )
    uniform_result = uniform.run([b"", b"A00", b"AB0"])
    assert uniform_result.target_reached
    assert (tmp_path / "guided" / "summary.json").exists()
    assert (tmp_path / "uniform" / "summary.json").exists()


def test_identical_configuration_produces_identical_execution_sequence(
        tmp_path: Path):
    def run(output: Path):
        ir = build_example_ir()
        campaign = _make_campaign(
            ir,
            scheduler=GuidedScheduler(epsilon=0.2, random_seed=42),
            mutator=BasicMutator(random_seed=42),
            output=output,
            max_executions=200,
        )
        result = campaign.run(example_seeds())
        records = [json.loads(line) for line in
                   (output / "metrics.jsonl").read_text().splitlines()]
        stable = [(record["execution"], record["candidate_id"],
                   record["parent_distance"], record["candidate_distance"],
                   record["retained"], record["target_reached"])
                  for record in records]
        return result, stable

    first_result, first_records = run(tmp_path / "first")
    second_result, second_records = run(tmp_path / "second")
    assert first_records == second_records
    assert first_result.executions == second_result.executions
    assert first_result.target_reached == second_result.target_reached


def test_target_reaching_input_can_be_replayed(tmp_path: Path):
    ir = build_example_ir()
    campaign = _make_campaign(ir, output=tmp_path / "out", max_executions=50)
    result = campaign.run([b""])
    assert result.target_reached
    reproducer = (tmp_path / "out" / "target_reaching_input.bin").read_bytes()
    replay_ir = build_example_ir()
    replay = _make_campaign(replay_ir, max_executions=1)
    replayed = replay.execute_input(reproducer)
    assert replayed.target_reached
    assert replayed.distance == 0


def test_target_without_static_path_is_reported_as_unknown():
    ir = build_example_ir()
    ir.blocks["isolated"] = BasicBlock(
        "isolated", str(EXAMPLES / "isolated.py"), "isolated", "f", 1, 1)
    target_id = "isolated"
    campaign = GuidedCampaign(
        ir=ir,
        target=BasicBlockTarget(target_id),
        adapter=example_adapter(),
        corpus=GuidedCorpus(10),
        scheduler=GuidedScheduler(epsilon=1.0, random_seed=0),
        mutator=BasicMutator(random_seed=0),
        config=CampaignConfig(max_executions=3, random_seed=0),
    )
    result = campaign.run([b"", b"A00"])
    assert not result.target_reached
    assert result.best_distance is None
    assert result.termination_reason == "max_executions"


def test_unmapped_runtime_events_are_counted():
    ir = build_example_ir()
    events = [TraceEvent(0, 0, "/not/in/ir.py", "missing", 10, "line")]
    mapped = map_trace(events, ir)
    assert len(mapped.unresolved) == 1
    assert mapped.blocks == []


def test_cli_guided_command_runs_end_to_end(tmp_path: Path, monkeypatch):
    ir = build_example_ir()
    ir_path = tmp_path / "program_ir.json"
    ir.to_json(ir_path)
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    (seeds / "seed").write_bytes(b"ABC")
    out = tmp_path / "cli-out"
    arguments = [
        "stateforge",
        "guided",
        "--ir", str(ir_path),
        "--target-bb", target_block_id(ir),
        "--corpus", str(seeds),
        "--adapter", "examples.m1_adapter:build_adapter",
        "--out", str(out),
        "--max-execs", "5",
        "--random-seed", "42",
    ]
    monkeypatch.setattr(sys, "argv", arguments)
    assert main() == 0
    summary = json.loads((out / "summary.json").read_text())
    assert summary["target_reached"] is True
    assert summary["termination_reason"] == "target_reached"


def test_cli_rejects_invalid_target(tmp_path: Path, monkeypatch, capsys):
    ir = build_example_ir()
    ir_path = tmp_path / "program_ir.json"
    ir.to_json(ir_path)
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    (seeds / "seed").write_bytes(b"ABC")
    arguments = [
        "stateforge",
        "guided",
        "--ir", str(ir_path),
        "--target-bb", "missing",
        "--corpus", str(seeds),
        "--adapter", "examples.m1_adapter:build_adapter",
        "--out", str(tmp_path / "out"),
    ]
    monkeypatch.setattr(sys, "argv", arguments)
    assert main() == 2
    assert "not found" in capsys.readouterr().err
