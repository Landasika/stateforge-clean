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
from stateforge.fuzzing.feedback.structural import StructuralFeedback
from stateforge.fuzzing.corpus_manager import CorpusManager


class CandidateCollector:
    def __init__(self, ir: ProgramIR, session: TraceSession,
                 feedback: StructuralFeedback,
                 corpus: CorpusManager | None,       
                 recorder: ExperimentRecorder, epoch: int,
                 on_save=None,                      
                 execution: ExecutionContext | None = None,   
                 state_ledger=None,                
                 state_novelty: bool = False):    
        self.ir = ir
        self.session = session
        self.feedback = feedback
        self.corpus = corpus
        self.recorder = recorder
        self.epoch = epoch
        self.on_save = on_save
        self.execution = execution if execution is not None else ExecutionContext()
        self.state_ledger = state_ledger
        self.state_novelty = state_novelty          
        self.lifecycle_failures = 0         
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
        obs = self.feedback.observe(mapped)         
        cid = None
        keep_for_state = self.state_novelty and bool(state_novel)
        if self.corpus is not None and (obs.interesting or keep_for_state):
            cid = self.corpus.save(
                data, self.epoch, len(obs.new_blocks),
                len(obs.new_edges), len(obs.blocks), len(obs.edges),
                interesting_reason=("state_novel" if keep_for_state
                                    and not obs.interesting
                                    else "new_structure"))
            if cid and self.on_save:
                self.on_save()                       
        self.feedback.update_global_coverage(obs.blocks, obs.edges)
        feedback_s = time.monotonic() - t1
        self.recorder.tick(exec_s, feedback_s,
                           len(self.feedback.global_blocks),
                           len(self.feedback.global_edges),
                           cid is not None, cid, obs.score)
        return obs
