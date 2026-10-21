from __future__ import annotations
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from stateforge.core.ir import ProgramIR
from stateforge.runtime.mapper import map_trace
from stateforge.runtime.tracer import TraceSession
from stateforge.state.extractor import StateFactCandidate, StateOperation


@dataclass
class StepResult:
    action: str
    request: dict
    ok: bool
    write_block: str | None
    n_covered: int
    target_block_covered: bool = False
    blocking: str | None = None       


@dataclass
class PlanExecution:
    steps: list[StepResult] = field(default_factory=list)
    target_covered: bool = False
    replanned: bool = False
    hits: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _load_target_module(target_path: str | Path):
    path = Path(target_path).resolve()
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod


def _expected_write_block(facts: list[StateFactCandidate],
                          source_file: str, arm: str,
                          arm_line: tuple[int, int]) -> str | None:
    
    for f in facts:
        if (f.operation == StateOperation.WRITE
                and arm_line[0] <= f.lineno <= arm_line[1]
                and f.block_id is not None
                and Path(f.source_file).resolve() == Path(source_file).resolve()):
            return f.block_id
    return None


def _arm_lines(arms, arm: str) -> tuple[int, int]:
    for name, s, e in arms:
        if name == arm:
            return (s, e)
    return (0, 0)


def execute_plan(segment, target_module, ir: ProgramIR,
                 facts: list[StateFactCandidate], target_block: str,
                 source_file: str, arms, reset=True) -> PlanExecution:
    
    result = PlanExecution()
    if reset:
        reset_fn = getattr(target_module, "reset_state", None)
        if callable(reset_fn):
            reset_fn()

    target_fn = getattr(target_module, "target", None)
    if not callable(target_fn):
        result.notes.append("no target() entry on module")
        return result

    root = str(Path(source_file).resolve().parent)
    with TraceSession(root=root) as session:
        for step in segment.steps:
            arm = step.action.removeprefix("POST op=")
            arm_line = _arm_lines(arms, arm)
            wblock = _expected_write_block(facts, source_file, arm, arm_line)
            payload = json.dumps({"json": step.json}).encode()
            with session.request() as rid:
                exc: Exception | None = None
                try:
                    target_fn(payload)
                except Exception as e:            
                    exc = e
            evs = [e for e in session.events if e.request_id == rid]
            covered = set(map_trace(evs, ir).blocks)
            hit_target = target_block in covered
            if exc is not None:
                ok = False
                blocking = f"exception:{type(exc).__name__}:{exc}"
            elif wblock is None:
                ok = hit_target                  
                blocking = None if ok else "target block not covered"
            else:
                ok = wblock in covered
                blocking = None if ok else (
                    f"write block {wblock} not covered"
                    f" (guard rejected, arm lines {arm_line[0]}-{arm_line[1]})")
            result.steps.append(StepResult(
                action=step.action, request=dict(step.json), ok=ok,
                write_block=wblock, n_covered=len(covered),
                target_block_covered=hit_target, blocking=blocking))
            result.target_covered = result.target_covered or hit_target

    hits = getattr(target_module, "HITS", None)
    result.hits = list(hits) if isinstance(hits, list) else []
    return result


def execute_plan_for_block(ir: ProgramIR,
                           facts: list[StateFactCandidate],
                           target_block: str,
                           source_file: str,
                           max_replan: int = 1) -> PlanExecution:
    
    from stateforge.state.goal_to_plan import dispatch_arms, plan_for_block

    arms = dispatch_arms(source_file)
    mod = _load_target_module(source_file)
    attempt = plan_for_block(ir, facts, target_block)
    if attempt is None:
        return PlanExecution(notes=["planning produced no chain"])
    _goal, segment = attempt
    result = execute_plan(segment, mod, ir, facts, target_block,
                          source_file, arms)
    if result.target_covered:
        return result
    replans = 0
    while not result.target_covered and replans < max_replan:
        replans += 1
        retry = plan_for_block(ir, facts, target_block)
        if retry is None:
            result.notes.append("replan: no chain derived")
            break
        _g2, segment2 = retry
        second = execute_plan(segment2, mod, ir, facts, target_block,
                              source_file, arms)
        second.replanned = True
        second.notes.append(
            f"replan #{replans}(首链失败:"
            + "; ".join(f"{s.action}:{s.blocking}"
                        for s in result.steps if not s.ok) + ")")
        second.steps = result.steps + second.steps   
        result = second
    return result
