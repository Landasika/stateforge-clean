from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from stateforge.core.model import PlanSegment, PlanStep
from stateforge.state.planning.binding import BindingContext
from stateforge.state.planning.goals import GoalSpec


@dataclass
class StepTrace:
    step: PlanStep
    route: str
    status: int
    body: Any = None


@dataclass
class GoalResult:
    goal: str
    hit: bool
    reason: str = ""
    steps: list[StepTrace] = field(default_factory=list)
    final_state: dict = field(default_factory=dict)


class ReplayExecutor:
    

    def __init__(self, wsgi_app=None, salt: str | None = None, base_url: str | None = None):
        if base_url:
            self.client = httpx.Client(base_url=base_url, timeout=10.0)
        elif wsgi_app is not None:
            self.client = httpx.Client(
                transport=httpx.WSGITransport(app=wsgi_app), base_url="http://replay"
            )
        else:
            raise ValueError("wsgi_app 或 base_url 必须给一个")
        self.salt = salt

    def run_segment(self, segment: PlanSegment, goal: GoalSpec,
                    checker: Callable[..., GoalResult] | None = None,
                    budget_ms: float = 10000.0) -> GoalResult:
        ctx = BindingContext(salt=self.salt)
        result = GoalResult(goal=segment.goal, hit=False)
        for step in segment.steps:
            route, json_body, headers = ctx.render_step(step)
            json_body = {k: _coerce(v) for k, v in (json_body or {}).items()}
            method = step.action.partition(" ")[0].lower()
            resp = self.client.request(method, route, json=json_body or None, headers=headers)
            body = _safe_json(resp)
            result.steps.append(StepTrace(step, route, resp.status_code, body))
            ctx.absorb(step.extract, body)
            if resp.status_code >= 400:
                result.reason = f"blocked at {step.action} → {resp.status_code}"
                return result
        if checker is not None:
            from stateforge.state.planning.checkers import verify_request

            vreq = verify_request(segment.goal, ctx)
            verify = (None, {}) if vreq is None else self.get(
                vreq["route"], vreq.get("headers", {}).get("Authorization", "").replace("Bearer ", "") or None
            )
            return checker(result, ctx, verify)
        result.hit = True  
        result.reason = "chain completed"
        return result

    def get(self, route: str, token: str | None = None) -> tuple[int, Any]:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        resp = self.client.get(route, headers=headers)
        return resp.status_code, _safe_json(resp)


def _safe_json(resp) -> Any:
    try:
        return resp.json()
    except Exception:  
        return resp.text


def _coerce(value):
    
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return value
