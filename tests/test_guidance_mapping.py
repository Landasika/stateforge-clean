
from pathlib import Path

from stateforge.analysis.static.icfg import build_icfg
from stateforge.core.ir import BasicBlock, ProgramIR
from stateforge.fuzzing.feedback.corpus import GuidedCorpus
from stateforge.fuzzing.guidance.campaign import (
    CampaignConfig,
    GuidedCampaign,
)
from stateforge.fuzzing.guidance.mutator import BasicMutator
from stateforge.fuzzing.guidance.scheduler import GuidedScheduler
from stateforge.fuzzing.guidance.target import BasicBlockTarget, TargetManager
from stateforge.runtime.mapper import MappedTrace, map_trace
from stateforge.runtime.tracer import TraceSession
from tests.helpers import build_example_ir, example_adapter, target_block_id


def test_proximity_is_not_a_target_hit():
    ir = build_example_ir()
    block_id = target_block_id(ir)
    manager = TargetManager(ir, BasicBlockTarget(block_id))
    predecessor = ir.incoming(block_id)[0].src
    trace = MappedTrace(blocks=[predecessor])
    assert manager.distance_for_trace(trace) == 1
    assert not manager.reached(trace)


def test_static_target_id_matches_dynamic_mapped_block():
    ir = build_example_ir()
    block_id = target_block_id(ir)
    manager = TargetManager(ir, BasicBlockTarget(block_id))
    session = TraceSession(Path(__file__).resolve().parents[1] / "examples")
    with session.trace_execution():
        with session.request() as rid:
            example_adapter().execute(b"ABC")
    events = session.drain_request_events(rid)
    mapped = map_trace(events, ir)
    assert block_id in set(mapped.blocks)
    assert manager.reached(mapped)
    assert not mapped.unresolved


def test_consecutive_events_are_not_automatically_valid_icfg_edges(
        tmp_path: Path):
    source = tmp_path / "app.py"
    source.write_text(
        "def f():\n"
        "    return 1\n"
        "def g():\n"
        "    return 2\n",
        encoding="utf-8",
    )
    namespace: dict = {}
    exec(compile(source.read_text(), str(source), "exec"), namespace)
    ir = build_icfg(tmp_path)
    f_exit = ir.functions["app.f"].exit
    g_entry = ir.functions["app.g"].entry

    class Adapter:
        def execute(self, data: bytes):
            namespace["f"]()
            namespace["g"]()

    session = TraceSession(tmp_path)
    with session.trace_execution():
        with session.request() as rid:
            Adapter().execute(b"x")
    events = session.drain_request_events(rid)
    mapped = map_trace(events, ir)
    assert (f_exit, g_entry) in mapped.edges
    assert all(edge in {(e.src, e.dst) for e in ir.edges}
               for edge in mapped.edges if edge != (f_exit, g_entry))

    campaign = GuidedCampaign(
        ir=ir,
        target=BasicBlockTarget(ir.functions["app.f"].entry),
        adapter=Adapter(),
        corpus=GuidedCorpus(10),
        scheduler=GuidedScheduler(epsilon=0.0, random_seed=0),
        mutator=BasicMutator(random_seed=0),
        config=CampaignConfig(max_executions=1, random_seed=0),
        session=TraceSession(tmp_path),
    )
    result = campaign.execute_input(b"x")
    assert (f_exit, g_entry) not in result.covered_edges
    assert campaign.session.events == []


def test_unresolved_events_are_counted_by_campaign(tmp_path: Path):
    source = tmp_path / "external.py"
    source.write_text(
        "def external(data):\n"
        "    return len(data)\n",
        encoding="utf-8",
    )
    namespace: dict = {}
    exec(compile(source.read_text(), str(source), "exec"), namespace)

    class Adapter:
        def execute(self, data: bytes):
            namespace["external"](data)

    ir = ProgramIR()
    ir.blocks["bb"] = BasicBlock("bb", str(tmp_path / "app.py"), "app",
                                 "target", 1, 1)
    campaign = GuidedCampaign(
        ir=ir,
        target=BasicBlockTarget("bb"),
        adapter=Adapter(),
        corpus=GuidedCorpus(10),
        scheduler=GuidedScheduler(epsilon=0.0, random_seed=0),
        mutator=BasicMutator(random_seed=0),
        config=CampaignConfig(max_executions=1, random_seed=0),
        session=TraceSession(None),
    )
    result = campaign.execute_input(b"x")
    assert result.covered_blocks == frozenset()
    assert result.unresolved_events > 0
    assert campaign.mapping_failures == result.unresolved_events
    assert result.distance is None
    assert not result.target_reached
    assert campaign.session.events == []
