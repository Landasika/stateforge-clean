from __future__ import annotations
from stateforge.core.model import AppModel, PlanStep
from stateforge.state.planning.goals import GoalSpec, auth_provisioning, register_step
JSON_FILL = {
    "username": "@fresh:u",
    "password": "@fresh:pw",
    "items": "@items",
    "coupon_code": "SAVE10",
    "amount": "100",
    "role": "admin",
}


def uses_token(steps: list[PlanStep]) -> bool:
    
    return any(
        s.headers.get("Authorization", "").split()[-1:] == ["?token"] for s in steps
    )


def produces_token(steps: list[PlanStep]) -> bool:
    return any(v == "?token" for s in steps for v in s.extract.values())


def ensure_auth(steps: list[PlanStep]) -> list[PlanStep]:
    
    if not uses_token(steps):
        return steps
    has_login = any(s.action.endswith("/auth/login") for s in steps)
    has_register = any(s.action.endswith("/auth/register") for s in steps)
    if has_login and has_register:
        return steps
    if has_login and not has_register:
        return [register_step()] + steps
    return auth_provisioning() + steps


def resource_completion(model: AppModel, ep_index: dict, goal: GoalSpec,
                        steps: list[PlanStep],
                        to_step) -> list[PlanStep]:
    
    used: set[str] = set()
    for s in steps:
        for v in list(s.path.values()) + list(s.json.values()):
            if isinstance(v, str) and v.startswith("?"):
                used.add(v[1:])
    bound = {slot.lstrip("?") for s in steps for slot in s.extract.values()}
    if not (used - bound):
        return steps
    for ep in model.endpoints:
        if ep.methods[0] == "POST" and "id" in ep.observes and "/auth/" not in ep.route:
            create = to_step(ep_index, f"POST {ep.route}", goal)
            
            insert_at = 0
            for i, s in enumerate(steps):
                if s.action.endswith("/auth/login"):
                    insert_at = i + 1
            return steps[:insert_at] + [create] + steps[insert_at:]
    return steps
