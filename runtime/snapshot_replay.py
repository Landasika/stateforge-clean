from __future__ import annotations
from stateforge.core.model import PlanSegment
from stateforge.runtime.replay import GoalResult, StepTrace, _coerce, _safe_json
from stateforge.state.planning.binding import BindingContext
from stateforge.state.planning.checkers import CHECKERS, verify_request
from stateforge.state.planning.goals import GoalSpec
from stateforge.runtime.snapshot.client import CheckpointHandle


class SnapshotReplay:
    def __init__(self, ckpt: CheckpointHandle, salt: str | None = None):
        self.ckpt = ckpt
        self.salt = salt

    def run_segment(self, segment: PlanSegment, goal: GoalSpec,
                    checker=None) -> GoalResult:
        ctx = BindingContext(salt=self.salt)
        steps = segment.steps
        vreq_probe = verify_request(goal.name, ctx)
        has_verify = vreq_probe is not None

        def request_fn(i, rs):
            for j in range(len(rs)):        
                if j < len(steps):
                    ctx.absorb(steps[j].extract, rs[j].get("body"))
            if i < len(steps):
                route, json_body, headers = ctx.render_step(steps[i])
                return {"method": steps[i].action.partition(" ")[0],
                        "route": route,
                        "json": {k: _coerce(v) for k, v in (json_body or {}).items()} or None,
                        "headers": headers or None}
            vreq = verify_request(goal.name, ctx)   
            return vreq

        out = self.ckpt.serve(request_fn, quota=len(steps) + (1 if has_verify else 0))

        result = GoalResult(goal=segment.goal, hit=False)
        for step, resp in zip(steps, out.responses):
            result.steps.append(StepTrace(step, step.action.partition(" ")[2],
                                          resp["status"], resp.get("body")))
            ctx.absorb(step.extract, resp.get("body"))
        for resp in out.responses:          
            if resp["status"] is not None and resp["status"] >= 400:
                idx = out.responses.index(resp)
                where = steps[idx].action if idx < len(steps) else "verify"
                result.reason = f"blocked at {where} → {resp['status']}"
                return result
        if not has_verify:
            check = checker or CHECKERS.get(goal.name)
            return check(result, ctx, (None, {}))
        verify = (out.responses[-1]["status"], out.responses[-1].get("body") or {})
        check = checker or CHECKERS.get(goal.name)
        return check(result, ctx, verify)
