
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
              max_seconds: float | None = None,
              max_corpus_size: int = 100):
    ir = build_example_ir()
    config = CampaignConfig(
        max_executions=max_executions,
        max_seconds=max_seconds,
        random_seed=7,
        epsilon=0.0,
        stop_on_target=stop_on_target,
        fault_policy=fault_policy,
        output_dir=output,
        max_corpus_size=max_corpus_size,
        progress_every=10,
    )
    return GuidedCampaign(
        ir=ir,
        target=BasicBlockTarget(target_block_id(ir)),
        adapter=example_adapter(),
        corpus=GuidedCorpus(max_corpus_size),
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
    assert (out / "target_archive").is_dir()


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


class FailAfterExecuteAdapter:
    def __init__(self, exception: type[BaseException]):
        self.exception = exception

    def execute(self, data: bytes):
        from examples.m1_target import target
        target(data)
        raise self.exception("boom")


def test_repeated_executions_keep_feedback_isolated():
    campaign = _campaign(max_executions=1000)
    results = []
    for index in range(300):
        data = b"A00" if index % 2 == 0 else b"ZZZ"
        result = campaign.execute_input(data)
        results.append((data, result))
        assert campaign.session.events == []
        assert campaign.session._request_indices == {}
    for data, result in results:
        if data == b"A00":
            assert result.distance == 10
            assert not result.target_reached
        else:
            assert not result.target_reached
    assert campaign.total_trace_events > 0


def test_exception_path_drains_trace_and_next_execution_is_isolated():
    campaign = _campaign(max_executions=10)
    campaign.adapter = FailAfterExecuteAdapter(RuntimeError)
    failed = campaign.execute_input(b"ZZZ")
    assert failed.error == "RuntimeError: boom"
    assert campaign.session.events == []
    campaign.adapter = example_adapter()
    healthy = campaign.execute_input(b"A00")
    assert healthy.error is None
    assert healthy.distance == 10
    assert healthy.covered_blocks
    assert campaign.session.events == []


def test_base_exception_drains_trace_before_propagating():
    campaign = _campaign(max_executions=10)
    campaign.adapter = FailAfterExecuteAdapter(KeyboardInterrupt)
    with pytest.raises(KeyboardInterrupt):
        campaign.execute_input(b"ZZZ")
    assert campaign.session.events == []
    campaign.adapter = example_adapter()
    healthy = campaign.execute_input(b"A00")
    assert healthy.error is None
    assert healthy.distance == 10


def test_archived_targets_are_persisted_outside_active_corpus(tmp_path: Path):
    out = tmp_path / "out"
    campaign = _campaign(output=out, max_executions=3,
                         stop_on_target=False, max_corpus_size=2)
    result = campaign.run([b"ABC", b"ABC0", b"ABC00"])
    assert result.target_reached
    assert result.archived_targets == 1
    assert len(campaign.corpus) == 2
    files = list((out / "target_archive").glob("*.bin"))
    assert len(files) == 1
    assert files[0].read_bytes() in (b"ABC", b"ABC0", b"ABC00")


def test_config_legacy_scheduler_maps_to_policies():
    uniform = CampaignConfig(scheduler_name="uniform")
    assert uniform.selection_policy == "uniform"
    assert uniform.energy_policy == "fixed"
    guided = CampaignConfig(scheduler_name="guided")
    assert guided.selection_policy == "distance"
    assert guided.energy_policy == "distance"


def test_config_keeps_explicit_policies():
    config = CampaignConfig(selection_policy="uniform", energy_policy="distance",
                            fixed_energy=4)
    assert config.selection_policy == "uniform"
    assert config.energy_policy == "distance"
    assert config.fixed_energy == 4


def test_campaign_builds_scheduler_from_policies():
    campaign = _campaign()
    campaign.config.selection_policy = "uniform"
    campaign.config.energy_policy = "fixed"
    campaign.config.fixed_energy = 3
    built = GuidedCampaign(
        ir=build_example_ir(),
        target=BasicBlockTarget(target_block_id(build_example_ir())),
        adapter=example_adapter(),
        config=campaign.config)
    assert built.scheduler.selection_policy == "uniform"
    assert built.scheduler.energy_policy == "fixed"
    assert built.scheduler.fixed_energy == 3
