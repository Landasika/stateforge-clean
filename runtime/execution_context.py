from __future__ import annotations
import gc
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Protocol, runtime_checkable
from stateforge.runtime.snapshot.l2_sqlite import (L2Sqlite,
                                                 SnapshotConsistencyError)
if TYPE_CHECKING:                                    
    from stateforge.state.runtime_observer import RuntimeObserver, StateObservation
class LifecycleError(RuntimeError):
    pass
ISOLATION_NONE = "none"
ISOLATION_RESET = "reset"
ISOLATION_SNAPSHOT = "snapshot"
RESET_HOOK_ATTR = "reset_state"        
SNAPSHOT_FILES_ATTR = "SF_STATE_FILES"   
MEMORY_RESET_ATTR = "SF_MEMORY_RESET"    
OBSERVER_ATTR = "sf_state_observer"      
@runtime_checkable
class StateLifecycle(Protocol):
    name: str
    isolation: str

    def establish_baseline(self) -> None: ...
    def begin_run(self) -> None: ...
    def end_run(self) -> None: ...


class NoopLifecycle:
    

    name = "noop"
    isolation = ISOLATION_NONE
    def establish_baseline(self) -> None:
        pass

    def begin_run(self) -> None:
        pass

    def end_run(self) -> None:
        pass


def _fail(hook: Callable[[], Any], what: str) -> None:
    try:
        hook()
    except LifecycleError:
        raise
    except Exception as exc:                          
        raise LifecycleError(f"{what} 失败({getattr(hook, '__name__', hook)}): "
                             f"{exc}") from exc


class ResetLifecycle:
    

    def __init__(self, reset_hooks: Iterable[Callable[[], None]]):
        self.reset_hooks = list(reset_hooks)
        if not self.reset_hooks:
            raise ValueError("ResetLifecycle 至少需要一个 reset 钩子")
        self.name = "reset"
        self.isolation = ISOLATION_RESET

    def establish_baseline(self) -> None:
        pass                                          

    def begin_run(self) -> None:
        for hook in self.reset_hooks:
            _fail(hook, "reset 钩子")

    def end_run(self) -> None:
        pass


class SnapshotLifecycle:
    

    BASELINE = "baseline"

    def __init__(self, files: Iterable[str | Path] = (),
                 memory_hooks: Iterable[Callable[[], None]] = (),
                 pre_restore_hooks: Iterable[Callable[[], None]] = (),
                 gc_before_restore: bool = True):
        self.files = [Path(f) for f in files]
        self.memory_hooks = list(memory_hooks)
        self.pre_restore_hooks = list(pre_restore_hooks)
        self.gc_before_restore = gc_before_restore
        if not self.files and not self.memory_hooks:
            raise ValueError("SnapshotLifecycle 需要 files 或 memory_hooks 之一")
        self.name = "snapshot"
        self.isolation = ISOLATION_SNAPSHOT
        self._l2 = [L2Sqlite(f, tpl_root=f.parent / f".sf_tpl_{f.name}")
                    for f in self.files]
        self._established = False

    def establish_baseline(self) -> None:
        
        for l2, path in zip(self._l2, self.files):
            try:
                l2.snapshot_template(self.BASELINE)   
            except (OSError, sqlite3.Error,
                    SnapshotConsistencyError) as exc:
                raise LifecycleError(
                    f"基线捕获失败({path}): {exc}") from exc
            if not l2.template_exists(self.BASELINE):
                raise LifecycleError(f"基线模板未建成({path})")
        self._established = True

    def begin_run(self) -> None:
        pass                                          

    def end_run(self) -> None:
        if not self._established:
            raise LifecycleError("end_run 前未 establish_baseline(内部错误)")
        for hook in self.pre_restore_hooks:           
            _fail(hook, "pre-restore 钩子(关连接)")
        if self.gc_before_restore:                    
            gc.collect()
        for l2, path in zip(self._l2, self.files):    
            if not l2.template_exists(self.BASELINE):
                raise LifecycleError(
                    f"基线模板丢失({path})——隔离失效,fail-closed")
            try:
                l2.restore(self.BASELINE)
            except (OSError, sqlite3.Error,
                    SnapshotConsistencyError) as exc:
                raise LifecycleError(f"基线还原失败({path}): {exc}") from exc
        for hook in self.memory_hooks:                
            _fail(hook, "memory-reset 钩子")


@dataclass(frozen=True)
class ExecutionResult:
    

    data: bytes = b""
    observations: tuple["StateObservation", ...] = ()   
    lifecycle: str = "noop"
    isolation: str = ISOLATION_NONE
    response: Any = None


class ExecutionContext:
    
    def __init__(self, lifecycle: StateLifecycle | None = None,
                 observer: "RuntimeObserver | None" = None):
        self.lifecycle: StateLifecycle = lifecycle or NoopLifecycle()
        self.observer = observer            
        self.runs = 0
        self.observer_failures = 0
        self._poisoned: str | None = None
        self._in_run = False
        self._baseline_done = False

    @property
    def name(self) -> str:
        return self.lifecycle.name

    @property
    def isolation(self) -> str:
        return self.lifecycle.isolation

    @property
    def poisoned(self) -> bool:
        return self._poisoned is not None
    def _ensure_alive(self) -> None:
        if self._poisoned is not None:
            raise LifecycleError(
                f"上下文已污染(fail-closed),拒绝后续执行: {self._poisoned}")
    
    def begin_run(self) -> None:
        self._ensure_alive()
        if self._in_run:
            raise RuntimeError("begin_run 未配对 finish_run")
        try:
            if not self._baseline_done:
                self.lifecycle.establish_baseline()
                self._baseline_done = True
            self.lifecycle.begin_run()
        except LifecycleError as exc:
            self._poisoned = str(exc)
            raise
        self._in_run = True
    def finish_run(self, data: bytes = b"") -> ExecutionResult:
        
        if not self._in_run:
            raise RuntimeError("finish_run 未配对 begin_run")
        self._in_run = False
        observations: tuple = ()
        if self.observer is not None:
            try:
                observations = tuple(self.observer.observe())
            except Exception:                          
                self.observer_failures += 1            
        try:
            self.lifecycle.end_run()
        except LifecycleError as exc:
            self._poisoned = str(exc)
            raise
        self.runs += 1
        return ExecutionResult(data=data, observations=observations,
                               lifecycle=self.lifecycle.name,
                               isolation=self.lifecycle.isolation)
    def run(self, fn: Callable[[bytes], Any], data: bytes) -> ExecutionResult:
        self.begin_run()
        error: Exception | None = None
        try:
            fn(data)
        except Exception as exc:                       
            error = exc
        result = self.finish_run(data)                 
        if error is not None:
            raise error
        return result




def lifecycle_from_module(module, spec: str = ISOLATION_NONE) -> StateLifecycle:
    
    if spec in ("noop", ISOLATION_NONE):             
        return NoopLifecycle()
    if spec == ISOLATION_RESET:
        hook = getattr(module, RESET_HOOK_ATTR, None)
        if not callable(hook):
            raise LifecycleError(
                f"--lifecycle reset 需要靶模块提供 {RESET_HOOK_ATTR}()")
        return ResetLifecycle([hook])
    if spec == ISOLATION_SNAPSHOT:
        files = [str(f) for f in (getattr(module, SNAPSHOT_FILES_ATTR, ()) or ())]
        mem = getattr(module, MEMORY_RESET_ATTR, None)
        memory_hooks = [mem] if callable(mem) else []
        if not files and not memory_hooks:
            raise LifecycleError(
                f"--lifecycle snapshot 需要靶模块提供 {SNAPSHOT_FILES_ATTR}"
                f" 或 {MEMORY_RESET_ATTR}")
        return SnapshotLifecycle(files=files, memory_hooks=memory_hooks)
    raise ValueError(f"未知 lifecycle 规格: {spec!r}")

def observer_from_module(module) -> "RuntimeObserver | None":
    
    factory = getattr(module, OBSERVER_ATTR, None)
    if not callable(factory):
        return None
    return factory()




def audit_lifecycle_failure(out_dir: str | Path, record: dict) -> None:
    
    try:
        path = Path(out_dir) / "lifecycle_failures.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.time(), **record},
                                ensure_ascii=False) + "\n")
    except OSError:
        pass

@dataclass(frozen=True)
class StepRecord:
    

    index: int
    action: str
    status: object = None                 
    error: str | None = None              
    before: tuple = ()                    
    after: tuple = ()                     
    duration_ms: float = 0.0
    bindings: dict = field(default_factory=dict)   
    trace_span: tuple[int, int] = (0, 0)  


@dataclass(frozen=True)
class InputRecord:
    
    steps: tuple[StepRecord, ...] = ()
    lifecycle_failures: int = 0
    observer_failures: int = 0
class RequestLevelHarness:

    def __init__(self, execution: "ExecutionContext",
                 observer=None, bindings_fn=None, extra_observe=None):
        self.execution = execution
        self.observer = observer
        self.bindings_fn = bindings_fn
        self.extra_observe = extra_observe      

    def _observe(self, session, step=None, extra=None):
        if self.observer is None and extra is None:
            return ()
        out: list = []
        try:
            if session is not None:
                with session.untraced():
                    if self.observer is not None:
                        out.extend(self.observer.observe())
                    if extra is not None and step is not None:
                        out.extend(extra(step))
            else:
                if self.observer is not None:
                    out.extend(self.observer.observe())
                if extra is not None and step is not None:
                    out.extend(extra(step))
        except Exception:                          
            self._observer_failures += 1
            return ()
        return tuple(out)

    _observer_failures = 0

    def run_input(self, steps, execute_step, *,
                  trace_session=None, action_of=None) -> InputRecord:
        
        try:
            self.execution.begin_run()             
        except LifecycleError:
            return InputRecord(lifecycle_failures=1)

        records: list[StepRecord] = []
        for idx, step in enumerate(steps):
            before = self._observe(trace_session, step, self.extra_observe)
            t0 = time.monotonic()
            start_ev = len(trace_session.events) if trace_session else 0
            status, error = None, None
            try:
                if trace_session is not None:
                    with trace_session.request():
                        status = execute_step(step)
                else:
                    status = execute_step(step)
            except Exception as exc:               
                error = f"{type(exc).__name__}:{exc}"
            end_ev = len(trace_session.events) if trace_session else 0
            duration_ms = (time.monotonic() - t0) * 1000
            after = self._observe(trace_session, step,
                                  self.extra_observe)  
            bindings = dict(self.bindings_fn()) if self.bindings_fn else {}
            records.append(StepRecord(
                index=idx,
                action=action_of(idx, step) if action_of
                else str(step.get("method", "")) + " " + str(step.get("path", step)),
                status=status, error=error, before=before, after=after,
                duration_ms=round(duration_ms, 3), bindings=bindings,
                trace_span=(start_ev, end_ev)))

        try:
            self.execution.finish_run()            
        except LifecycleError:
            return InputRecord(steps=tuple(records), lifecycle_failures=1,
                               observer_failures=self._observer_failures)
        return InputRecord(steps=tuple(records),
                           observer_failures=self._observer_failures)
