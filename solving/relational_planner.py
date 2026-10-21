from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field
from typing import Mapping, Sequence
from stateforge.solving.vulnshop_state_bridge import (
    AppModelPath,
    _render_step,
    render_seed,
)
from stateforge.state.planning.backward import _to_step, plan_backward
from stateforge.state.planning.binding import BindingContext
from stateforge.state.planning.compat import ensure_auth, resource_completion
from stateforge.state.planning.goals import GoalSpec
from stateforge.state.relational import Const, Field, RelPredicate
@dataclass(frozen=True)
class BindingObligation:
    

    slot: str                     
    producers: tuple[str, ...]    
    consumers: tuple[str, ...]    
    note: str = ""


@dataclass(frozen=True)
class RelationalPlanCandidate:
    

    goal_id: str                          
    steps: tuple[dict, ...]               
    obligations: tuple[BindingObligation, ...] = ()
    conditional_on: tuple[str, ...] = ()  
    dropped_relations: tuple[str, ...] = ()   
    uncovered_relations: tuple[str, ...] = () 
    binding_conflicts: tuple[str, ...] = ()   
    notes: tuple[str, ...] = ()
    signature: str = ""                   

    def to_dict(self) -> dict:
        return {
            "goal_id": self.goal_id,
            "steps": [dict(s) for s in self.steps],
            "obligations": [{"slot": o.slot, "producers": list(o.producers),
                             "consumers": list(o.consumers), "note": o.note}
                            for o in self.obligations],
            "conditional_on": list(self.conditional_on),
            "dropped_relations": list(self.dropped_relations),
            "uncovered_relations": list(self.uncovered_relations),
            "binding_conflicts": list(self.binding_conflicts),
            "notes": list(self.notes),
            "signature": self.signature,
        }

@dataclass(frozen=True)
class VerifiedPlan:

    candidate: RelationalPlanCandidate
    achievement_status: str               
    relations_truth: str
    auth_binding_truth: str
    trace_covered: bool
    witness: dict | None                  
    failure_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"candidate": self.candidate.to_dict(),
                "achievement_status": self.achievement_status,
                "relations_truth": self.relations_truth,
                "auth_binding_truth": self.auth_binding_truth,
                "trace_covered": self.trace_covered,
                "witness": self.witness,
                "failure_reasons": list(self.failure_reasons)}




def _step_key(step: dict) -> tuple:
    return (step.get("method", "GET"), step.get("path", ""),
            json.dumps(step.get("json") or {}, sort_keys=True,
                       ensure_ascii=False))


def _action_label(step: dict) -> str:
    return f"{step.get('method', 'GET')} {step.get('path', '')}"


def _consumes_token(step: dict) -> bool:
    auth = (step.get("header") or {}).get("Authorization", "")
    return "?token" in str(auth)


def _produces_token(step: dict) -> bool:
    return "?token" in (step.get("extract") or {}).values()


def _final_action(amp: AppModelPath, goal) -> str | None:
    for ep in amp.model.endpoints:
        if ep.func == getattr(goal, "function", ""):
            return f"{ep.methods[0] if ep.methods else 'GET'} {ep.route}"
    return None


def _active_relations(goal, runtime_path_context
                      ) -> tuple[tuple, tuple[str], tuple[str]]:
    
    rels = tuple(getattr(goal, "relations", ()))
    pcs = tuple(getattr(goal, "path_conditions", ()))
    config_vars = {pc.var: pc for pc in pcs if pc.kind == "config"}
    if not runtime_path_context:
        return rels, (), tuple(sorted(config_vars))

    dropped: list[str] = []
    keep: list = []
    for rel in rels:
        conditional_vars = [
            v for v, pc in config_vars.items()
            if pc.source_line and rel.source_line
            and pc.source_line < rel.source_line
            and runtime_path_context.get(v) is False]
        if conditional_vars:
            dropped.append(f"{rel.render()}(条件 {conditional_vars} 为 False,"
                           f"不适用本执行)")
        else:
            keep.append(rel)
    active_flags = tuple(sorted(
        v for v in config_vars
        if runtime_path_context.get(v) is not False))
    return tuple(keep), tuple(dropped), active_flags
def detect_auth_rebinding(steps: Sequence[dict]) -> list[str]:
    logins = [i for i, s in enumerate(steps)
              if str(s.get("path", "")).endswith("/auth/login")]
    if len(logins) > 1:
        return [f"auth-rebinding:链内 {len(logins)} 次 login"
                f"(位置 {logins})——身份切换后,先前身份创建的资源与"
                f"后续消费步骤的 ?token 义务可能失效(执行验证裁决)"]
    return []




def plan_for_relational_goal(goal, amp: AppModelPath,
                             *, runtime_path_context: Mapping[str, bool] | None = None,
                             salt: str = "sf") -> RelationalPlanCandidate | None:
    
    final_action = _final_action(amp, goal)
    if final_action is None:
        return None

    rels, dropped, flags = _active_relations(goal, runtime_path_context)

    
    requires_atoms = sorted({v for _, v, d in amp.sstg.edges(data=True)
                             if d.get("kind") == "requires"})
    chains: list[list[dict]] = []
    obligations_notes: list[str] = []
    uncovered: list[str] = []
    for rel in rels:
        if not (isinstance(rel.right, Const)):
            if isinstance(rel.right, Field):        
                obligations_notes.append(
                    f"{rel.render()}:{rel.left.var} ≡ {rel.right.var} 的"
                    f"同一性经绑定义务保证(?token 单一主体),"
                    f"运行时探测+联合验证裁决")
            continue
        suffix = f".{rel.left.name}={rel.right.value}"
        atom = next((a for a in requires_atoms if a.endswith(suffix)), None)
        if atom is None:
            uncovered.append(f"{rel.render()}(SSTG 无生产者)")
            continue
        chains.append(render_seed(amp, atom, salt))
    
    
    ep_index = {(ep.methods[0], ep.route): ep for ep in amp.model.endpoints}
    spec = GoalSpec(name="relational_final", vuln_class="state",
                    kind="reach_state", target=None)
    final_ps = _to_step(ep_index, final_action, spec)
    plan_steps = ensure_auth([final_ps])
    plan_steps = resource_completion(amp.model, ep_index, spec,
                                     plan_steps, _to_step)
    ctx = BindingContext(salt=salt)
    base = [_render_step(ctx, ps) for ps in plan_steps]
    
    merged: list[dict] = []
    seen: set[tuple] = set()
    for chain in chains:
        for st in chain:
            k = _step_key(st)
            if k not in seen:
                seen.add(k)
                merged.append(st)
    for st in base:
        k = _step_key(st)
        if k not in seen:
            seen.add(k)
            merged.append(st)              
    final_key = _step_key(base[-1])
    final_steps = [s for s in merged if _step_key(s) == final_key]
    merged = [s for s in merged if _step_key(s) != final_key]
    merged.extend(final_steps)             

    
    labels = [_action_label(s) for s in merged]
    obligations: list[BindingObligation] = []
    token_consumers = tuple(l for l, s in zip(labels, merged)
                            if _consumes_token(s))
    if token_consumers:
        obligations.append(BindingObligation(
            slot="?token",
            producers=tuple(l for l, s in zip(labels, merged)
                            if _produces_token(s)),
            consumers=token_consumers,
            note="认证主体单一性:create/pay/ship 共用同一 token"
                 "(身份切换=义务破坏,验证期裁决)"))
    oid_consumers = tuple(l for l, s in zip(labels, merged)
                          if "?oid" in str(s.get("path", "")))
    if oid_consumers:
        obligations.append(BindingObligation(
            slot="?oid",
            producers=tuple(l for l, s in zip(labels, merged)
                            if "id" in (s.get("extract") or {})),
            consumers=oid_consumers,
            note="资源同一性:?oid 由 create 的 extract 重建,不写死 ID"))
    obligations.extend(
        BindingObligation(slot="relation", producers=(), consumers=(),
                          note=n) for n in obligations_notes)

    conflicts = detect_auth_rebinding(merged)

    signature = hashlib.sha256(json.dumps(
        {"goal": getattr(goal, "target_block", ""),
         "steps": [_step_key(s) for s in merged]},
        sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]

    return RelationalPlanCandidate(
        goal_id=getattr(goal, "target_block", ""),
        steps=tuple(merged),
        obligations=tuple(obligations),
        conditional_on=flags,
        dropped_relations=dropped,
        uncovered_relations=tuple(uncovered),
        binding_conflicts=tuple(conflicts),
        notes=(f"final-action: {final_action}",),
        signature=signature)
