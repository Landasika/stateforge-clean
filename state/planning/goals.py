from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

from stateforge.core.model import PlanStep


class ActorSpec(BaseModel):
    role: Literal["any_user", "other_user", "admin", "anonymous"] = "any_user"
    fresh_identity: bool = True


class GoalSpec(BaseModel):
    name: str
    vuln_class: str
    kind: Literal["reach_state", "forbidden_transition", "authz_replay"]
    target: str | None = None                 
    transition: tuple[str, str] | None = None  
    actor: ActorSpec = ActorSpec()
    max_depth: int = 8
    verify_endpoint: str | None = None
    
    drop_requires: list[str] = Field(default_factory=list)
    param_overrides: dict[str, str] = Field(default_factory=dict)
    
    step_template: list[PlanStep] = Field(default_factory=list)

ITEMS = [{"sku": "book", "price": 100, "qty": 1}]

VULNSHOP_GOALS: list[GoalSpec] = [
    GoalSpec(
        name="goal_workflow_bypass", vuln_class="workflow_bypass",
        kind="forbidden_transition", target="Order.status=SHIPPED",
        transition=("PAID", "SHIPPED"),
        drop_requires=["Order.status"],       
        verify_endpoint="GET /orders/<int:oid>",
    ),
    GoalSpec(
        name="goal_coupon_reuse", vuln_class="coupon_reuse",
        kind="reach_state", target="Coupon.used=1",
        step_template=[
            PlanStep(action="POST /auth/register", json={"username": "@fresh:u", "password": "@fresh:pw"}),
            PlanStep(action="POST /auth/login", json={"username": "@fresh:u", "password": "@fresh:pw"},
                     extract={"token": "?token"}),
            PlanStep(action="POST /orders", json={"items": "@items", "coupon_code": "SAVE10"},
                     headers={"Authorization": "Bearer ?token"}, extract={"id": "?oid1"}),
            PlanStep(action="POST /orders", json={"items": "@items", "coupon_code": "SAVE10"},
                     headers={"Authorization": "Bearer ?token"}, extract={"id": "?oid2"}),
        ],
        verify_endpoint="GET /coupons/<code>",
    ),
    GoalSpec(
        name="goal_idor", vuln_class="idor",
        kind="authz_replay", target="Order.status=CREATED",
        step_template=[
            
            PlanStep(action="POST /auth/register", json={"username": "@fresh:a", "password": "@fresh:pw"}),
            PlanStep(action="POST /auth/login", json={"username": "@fresh:a", "password": "@fresh:pw"},
                     extract={"token": "?token_a"}),
            PlanStep(action="POST /orders", json={"items": "@items"},
                     headers={"Authorization": "Bearer ?token_a"}, extract={"id": "?oid"}),
            PlanStep(action="POST /auth/register", json={"username": "@fresh:b", "password": "@fresh:pw"}),
            PlanStep(action="POST /auth/login", json={"username": "@fresh:b", "password": "@fresh:pw"},
                     extract={"token": "?token_b"}),
            PlanStep(action="GET /orders/<int:oid>", path={"oid": "?oid"},
                     headers={"Authorization": "Bearer ?token_b"}),
        ],
        verify_endpoint="GET /orders/<int:oid>",
    ),
    GoalSpec(
        name="goal_payment_bypass", vuln_class="payment_bypass",
        kind="reach_state", target="Order.status=PAID",
        param_overrides={"amount": "10"},      
        verify_endpoint="GET /orders/<int:oid>",
    ),
    GoalSpec(
        name="goal_privilege", vuln_class="privilege",
        kind="authz_replay", target="User.role=user",
        step_template=[
            
            PlanStep(action="GET /auth/me", headers={"Authorization": "Bearer ?token"},
                     extract={"id": "?uid"}),
            PlanStep(action="POST /admin/users/<int:uid>/role", json={"role": "admin"},
                     headers={"Authorization": "Bearer ?token"}, path={"uid": "?uid"}),
        ],
        verify_endpoint="GET /auth/me",
    ),
]


def auth_provisioning(prefix: str = "u") -> list[PlanStep]:
    
    return [
        PlanStep(action="POST /auth/register",
                 json={"username": f"@fresh:{prefix}", "password": "@fresh:pw"}),
        PlanStep(action="POST /auth/login",
                 json={"username": f"@fresh:{prefix}", "password": "@fresh:pw"},
                 extract={"token": "?token"}),
    ]


def register_step(prefix: str = "u") -> PlanStep:
    return PlanStep(action="POST /auth/register",
                    json={"username": f"@fresh:{prefix}", "password": "@fresh:pw"})
