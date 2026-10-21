from __future__ import annotations
import time
from stateforge.core.ir import ProgramIR
from stateforge.runtime.execution_context import (
    ExecutionContext,
    LifecycleError,
    audit_lifecycle_failure,
)
from stateforge.runtime.mapper import map_trace
from stateforge.runtime.tracer import TraceSession
from stateforge.fuzzing.recorder import ExperimentRecorder
from stateforge.fuzzing.feedback.frontier_feedback import FrontierDirectedFeedback
from stateforge.fuzzing.corpus_manager import CorpusManager


class FrontierCollector:
    def __init__(self, ir: ProgramIR, session: TraceSession,
                 feedback: FrontierDirectedFeedback, corpus: CorpusManager,
                 recorder: ExperimentRecorder, epoch: int, on_save=None,
                 execution: ExecutionContext | None = None,   
                 state_ledger=None,                
                 state_novelty: bool = False):    
        self.ir, self.session, self.feedback = ir, session, feedback
        self.corpus, self.recorder, self.epoch = corpus, recorder, epoch
        self.on_save = on_save
        self.execution = execution if execution is not None else ExecutionContext()
        self.state_ledger = state_ledger
        self.state_novelty = state_novelty          
        self.frontier_saves = 0          
        self.lifecycle_failures = 0      
        self._events_path = corpus.spool / "frontier_events.jsonl"

    def _lifecycle_failed(self, exc: LifecycleError):
        
        self.lifecycle_failures += 1
        audit_lifecycle_failure(self.recorder.dir, {
            "group": self.recorder.group, "epoch": self.epoch,
            "lifecycle": self.execution.lifecycle.name,
            "isolation": self.execution.lifecycle.isolation,
            "error": str(exc)})
    def handle(self, target, data: bytes):
        start = len(self.session.events)
        with self.session.request():
            t0 = time.monotonic()
            try:
                self.execution.begin_run()           
            except LifecycleError as exc:
                self._lifecycle_failed(exc)
                return None
            try:
                target(data)
            except Exception:                      
                pass
            exec_s = time.monotonic() - t0
        
        
        try:
            with self.session.untraced():
                result = self.execution.finish_run(data)
        except LifecycleError as exc:
            self._lifecycle_failed(exc)
            return None
        state_novel = ()
        if self.state_ledger is not None:
            state_novel = self.state_ledger.record(result.observations)
        t1 = time.monotonic()
        mapped = map_trace(self.session.events[start:], self.ir)
        cid_pre = CorpusManager.content_id(data)
        obs = self.feedback.observe(mapped, cid_pre)   
        cid = None
        keep_for_state = self.state_novelty and bool(state_novel)
        if obs.interesting or keep_for_state:
            cid = self.corpus.save(
                data, self.epoch, obs.new_blocks,
                obs.new_edges, len(mapped.block_hits),
                len(mapped.edge_kinds),
                distance=obs.distance,
                nearest_frontier=obs.nearest_frontier,
                interesting_reason=("state_novel" if keep_for_state
                                    and not obs.interesting
                                    else obs.reason))
            if cid and obs.reason in ("frontier_champion", "frontier_progress"):
                self.frontier_saves += 1
            if cid and self.on_save:
                self.on_save()
        self.feedback.commit(mapped, cid is not None)
        for ev in self.feedback.portfolio.drain_events():
            self._events_path.parent.mkdir(parents=True, exist_ok=True)
            with self._events_path.open("a", encoding="utf-8") as fh:
                fh.write(__import__("json").dumps(vars(ev) | {"edge": None},
                                                  ensure_ascii=False) + "\n")
        for ev in self.feedback.tracker.drain_lifecycle():
            self._events_path.parent.mkdir(parents=True, exist_ok=True)
            with self._events_path.open("a", encoding="utf-8") as fh:
                fh.write(__import__("json").dumps(ev, ensure_ascii=False) + "\n")
        feedback_s = time.monotonic() - t1
        self.recorder.tick(exec_s, feedback_s,
                           len(self.feedback.novelty.global_blocks),
                           len(self.feedback.novelty.global_edges),
                           cid is not None, cid, int(obs.score))
        return obs
