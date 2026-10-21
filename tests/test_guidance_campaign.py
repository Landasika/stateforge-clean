
import json
from pathlib import Path

import pytest

from stateforge.fuzzing.feedback.corpus import GuidedCorpus, seed_id_for
from stateforge.fuzzing.guidance.campaign import (
    CampaignConfig,
    GuidedCampaign,
)
from stateforge.fuzzing.guidance.scheduler import (
    EmptyCorpusError,
    GuidedScheduler,
)
from stateforge.fuzzing.guidance.target import BasicBlockTarget, StaleIRError
from tests.helpers import build_example_ir, example_adapter, target_block_id


class StagedMutator:
    operators = ("staged",)
    random_seed = 0

    def __init__(self):
        self.table = {
            b"": b"A00",
            b"A00": b"AB0",
            b"AB0": b"ABC",
            b"ABC": b"ABC",
        }

    def mutate(self, data: bytes, *, max_size: int,
               other: bytes | None = None) -> bytes:
        return self.table.get(bytes(data), b"ABC")[:max_size]


class RecordingScheduler(GuidedScheduler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected: list[str] = []

    def select(self, corpus):
        seed = super().select(corpus)
        self.selected.append(seed.seed_id)
        return seed


class BoomAdapter:
    def execute(self, data: bytes):
        raise RuntimeError("boom")


def _campaign(output: Path | None = None, scheduler=None, mutator=None,
              max_executions: int = 50, stop_on_target: bool = True,
              fault_policy: str = "continue",
              max_seconds: float | None = None):
    ir = build_example_ir()
    config = CampaignConfig(
        max_executions=max_executions,
        max_seconds=max_seconds,
        random_seed=7,
        epsilon=0.0,
        stop_on_target=stop_on_target,
        fault_policy=fault_policy,
        output_dir=output,
        max_corpus_size=100,
        progress_every=10,
    )
    return GuidedCampaign(
        ir=ir,
        target=BasicBlockTarget(target_block_id(ir)),
        adapter=example_adapter(),
        corpus=GuidedCorpus(100),
        scheduler=scheduler or GuidedScheduler(epsilon=0.0, random_seed=7),
        mutator=mutator or StagedMutator(),
        config=config,
    )


def test_budget_counts_initial_seed_executions():
    campaign = _campaign(max_executions=2)
    result = campaign.run([b"", b"A00", b"AB0"])
    assert result.executions == 2
    assert campaign.executions == 2
    assert result.termination_reason == "max_executions"


def test_initial_seed_can_reach_target_and_save_reproducer(tmp_path: Path):
    out = tmp_path / "out"
    campaign = _campaign(output=out, max_executions=5)
    result = campaign.run([b"ABC"])
    assert result.target_reached
    assert result.executions == 1
    assert result.executions_to_target == 1
    assert result.termination_reason == "target_reached"
    assert (out / "target_reaching_input.bin").read_bytes() == b"ABC"
    summary = json.loads((out / "summary.json").read_text())
    assert summary["target_reached"] is True
    assert summary["target_basic_block"] == result.target_block_id


def test_guided_campaign_reaches_target_and_metrics_are_complete(tmp_path: Path):
    out = tmp_path / "out"
    scheduler = RecordingScheduler(epsilon=0.0, random_seed=7)
    campaign = _campaign(output=out, scheduler=scheduler, max_executions=100)
    result = campaign.run([b""])
    assert result.target_reached
    assert result.executions <= 100
    assert result.best_distance == 0
    assert (out / "target_reaching_input.bin").read_bytes() == b"ABC"
    lines = (out / "metrics.jsonl").read_text().splitlines()
    assert len(lines) == result.executions
    records = [json.loads(line) for line in lines]
    assert records[-1]["target_reached"] is True
    assert records[-1]["candidate_distance"] == 0
    assert seed_id_for(b"AB0") in scheduler.selected


def test_distance_feedback_is_monotonic_across_initial_seeds(tmp_path: Path):
    out = tmp_path / "out"
    campaign = _campaign(output=out, max_executions=3)
    result = campaign.run([b"", b"A00", b"AB0"])
    records = [json.loads(line)
               for line in (out / "metrics.jsonl").read_text().splitlines()]
    distances = [record["candidate_distance"] for record in records]
    assert distances == [18, 10, 3]
    assert result.best_distance == 3
    assert records[-1]["parent_distance"] is None


def test_scheduler_selects_nearest_retained_seed():
    scheduler = RecordingScheduler(epsilon=0.0, random_seed=7)
    campaign = _campaign(scheduler=scheduler, max_executions=100)
    result = campaign.run([b"", b"A00", b"AB0"])
    assert result.target_reached
    assert seed_id_for(b"AB0") in scheduler.selected


def test_each_input_has_isolated_trace_feedback():
    campaign = _campaign(max_executions=20)
    first = campaign.execute_input(b"ZZZ")
    second = campaign.execute_input(b"ABC")
    target_id = campaign.target.block_id
    assert not first.target_reached
    assert target_id not in first.covered_blocks
    assert second.target_reached
    assert target_id in second.covered_blocks
    assert campaign.session.events == []


def test_unexpected_exception_continues_and_preserves_inputs(tmp_path: Path):
    out = tmp_path / "out"
    campaign = _campaign(output=out, max_executions=2)
    campaign.adapter = BoomAdapter()
    result = campaign.run([b"boom"])
    assert result.executions == 2
    assert result.unexpected_exceptions == 2
    assert result.target_reached is False
    assert result.termination_reason == "max_executions"
    crashes = list((out / "crashes").glob("*.bin"))
    assert len(crashes) == 2


def test_fault_policy_stop_terminates_cleanly(tmp_path: Path):
    out = tmp_path / "out"
    campaign = _campaign(output=out, max_executions=20, fault_policy="stop")
    campaign.adapter = BoomAdapter()
    result = campaign.run([b"boom"])
    assert result.executions == 1
    assert result.termination_reason == "fault"
    summary = json.loads((out / "summary.json").read_text())
    assert summary["unexpected_exceptions"] == 1


def test_empty_corpus_is_rejected():
    campaign = _campaign()
    with pytest.raises(EmptyCorpusError):
        campaign.run([])


def test_zero_second_budget_stops_before_execution(tmp_path: Path):
    out = tmp_path / "out"
    campaign = _campaign(output=out, max_seconds=0.0)
    result = campaign.run([b"ABC"])
    assert result.executions == 0
    assert result.termination_reason == "max_seconds"
    assert result.target_reached is False
    assert (out / "summary.json").exists()


def test_target_reaching_file_is_absent_when_target_is_not_reached(tmp_path: Path):
    out = tmp_path / "out"
    campaign = _campaign(output=out, max_executions=1)
    result = campaign.run([b""])
    assert not result.target_reached
    assert not (out / "target_reaching_input.bin").exists()
    assert (out / "corpus").is_dir()
    assert (out / "crashes").is_dir()


def test_trace_memory_is_released_between_executions(tmp_path: Path):
    campaign = _campaign(max_executions=100, mutator=StagedMutator())
    result = campaign.run([b""])
    assert result.executions > 5
    assert campaign.total_trace_events > 0
    assert len(campaign.session.events) == 0


def test_output_contract_and_configuration_metadata(tmp_path: Path):
    out = tmp_path / "out"
    campaign = _campaign(output=out, max_executions=5)
    result = campaign.run([b"ABC"])
    assert result.target_reached
    assert (out / "config.json").exists()
    assert (out / "summary.json").exists()
    assert (out / "metrics.jsonl").exists()
    configuration = json.loads((out / "config.json").read_text())
    assert configuration["target_basic_block"] == result.target_block_id
    assert configuration["source_hash"]
    assert configuration["initial_corpus"] == [seed_id_for(b"ABC")]
    assert configuration["config"]["random_seed"] == 7
    assert configuration["environment"]["python"]
    assert len(list((out / "corpus").glob("*.bin"))) >= 1


def test_stale_ir_requires_explicit_override(tmp_path: Path):
    source = tmp_path / "app.py"
    source.write_text("def f(x):\n    return x\n", encoding="utf-8")
    ir = build_example_ir()
    ir.metadata["source_hash"] = "0" * 64
    target = BasicBlockTarget(target_block_id(ir))
    with pytest.raises(StaleIRError):
        GuidedCampaign(ir, target, example_adapter(),
                       config=CampaignConfig(max_executions=1))
    campaign = GuidedCampaign(
        ir, target, example_adapter(),
        config=CampaignConfig(max_executions=1, allow_stale_ir=True))
    assert campaign.target_manager.stale
