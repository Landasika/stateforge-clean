from __future__ import annotations
from pydantic import BaseModel, Field
from stateforge.core.model import AppModel, Endpoint, Invariant, StateVar
class DraftAnnotation(BaseModel):
    policy_class: str            
    policy_name: str             
    file: str
    line: int                    
    code: str                    
    target: str = ""             
    var: str = ""
    rationale: str = ""


def draft_annotations(model: AppModel, llm_rationales: dict[str, str] | None = None) -> list[DraftAnnotation]:
    llm_rationales = llm_rationales or {}
    drafts: list[DraftAnnotation] = []
    inv_by_var = {i.var: i for i in model.invariants}
    sv_by_var = {sv.var: sv for sv in model.state_vars}

    for ep in model.endpoints:
        target = f"{ep.methods[0]} {ep.route}"
        for g in ep.guards:
            if g.kind == "owner":
                var = "Order.user_id" if any(True for _ in ep.effects) or True else ""
                drafts.append(DraftAnnotation(
                    policy_class="owner",
                    policy_name=f"order_owner_{ep.func}",
                    file=g.file, line=g.line,
                    code=f'ANOTA_EXECUTION.BLOCK(order["user_id"] == user["id"], msg="ANOTA_POLICY:order_owner_{ep.func}")',
                    target=target, var="Order.user_id",
                    rationale=llm_rationales.get("owner", "跨用户访问实体 = 违规"),
                ))
            elif g.kind == "role":
                drafts.append(DraftAnnotation(
                    policy_class="role",
                    policy_name="admin_required",
                    file=g.file, line=g.line,
                    code='ANOTA_EXECUTION.BLOCK(user["role"] == "admin", msg="ANOTA_POLICY:admin_required")',
                    target=target, var="User.role",
                    rationale=llm_rationales.get("role", "非特权角色执行特权操作 = 违规"),
                ))
        
        entity_of = lambda v: v.partition(".")[0]
        for eff in ep.effects:
            inv = inv_by_var.get(eff.var)
            sv = sv_by_var.get(eff.var)
            if inv and inv.legal_transitions and eff.value:
                legal_frms = {frm for frm, to in inv.legal_transitions if to == eff.value}
                domain = set(sv.domain or [])
                if legal_frms and domain - legal_frms - {eff.value}:
                    row, attr = _row_attr(eff.var)
                    drafts.append(DraftAnnotation(
                        policy_class="requires_state",
                        policy_name=f"{ep.func}_requires_{str(next(iter(legal_frms))).lower()}",
                        file=eff.file, line=eff.line,
                        code=f'ANOTA_EXECUTION.BLOCK({row}["{attr}"] == "{next(iter(legal_frms))}", msg="ANOTA_POLICY:{ep.func}_requires_{str(next(iter(legal_frms))).lower()}")',
                        target=target, var=eff.var,
                        rationale=llm_rationales.get("requires_state",
                            f"{eff.var} 合法前驱 = {sorted(legal_frms)},其余为非法迁移起点"),
                    ))
            if inv and inv.one_way:
                row, attr = _row_attr(eff.var)
                drafts.append(DraftAnnotation(
                    policy_class="single_use",
                    policy_name="coupon_single_use" if eff.var == "Coupon.used" else f"{attr}_single_use",
                    file=eff.file, line=eff.line,
                    code=f'ANOTA_EXECUTION.BLOCK(not {row}["{attr}"], msg="ANOTA_POLICY:{"coupon_single_use" if eff.var == "Coupon.used" else attr + "_single_use"}")',
                    target=target, var=eff.var,
                    rationale=llm_rationales.get("single_use", "单次性资源被重复消耗 = 违规"),
                ))
            if pay_like and sv and sv.label == "money" and eff.var.endswith("paid_amount"):
                entity = entity_of(eff.var)
                row, attr = _row_attr(eff.var)
                drafts.append(DraftAnnotation(
                    policy_class="pay_full",
                    policy_name="pay_full_amount",
                    file=eff.file, line=eff.line,
                    code=f'ANOTA_EXECUTION.BLOCK({row}["paid_amount"] + amount >= {row}["total"], msg="ANOTA_POLICY:pay_full_amount")',
                    target=target, var=eff.var,
                    rationale=llm_rationales.get("pay_full", "未付满即进入已付状态 = 违规"),
                ))

        
        
        
        pay_like = any(p.name == "amount" for p in ep.params)
        if pay_like and "paid_amount" in ep.observes \
                and not any(d.policy_class == "pay_full" and d.target == target for d in drafts):
            anchor = ep.effects[0] if ep.effects else None
            row = _row_attr("Order.paid_amount")[0]
            drafts.append(DraftAnnotation(
                policy_class="pay_full",
                policy_name="pay_full_amount",
                file=ep.file, line=(anchor.line if anchor else ep.line),
                code=f'ANOTA_EXECUTION.BLOCK({row}["paid_amount"] + amount >= {row}["total"], msg="ANOTA_POLICY:pay_full_amount")',
                target=target, var="Order.paid_amount",
                rationale=llm_rationales.get("pay_full", "未付满即进入已付状态 = 违规"),
            ))
    return _dedup(drafts)


def _row_attr(var: str) -> tuple[str, str]:
    entity, _, attr = var.partition(".")
    return entity.lower(), attr


def _dedup(drafts: list[DraftAnnotation]) -> list[DraftAnnotation]:
    seen: set[tuple[str, str, int, str]] = set()
    out = []
    for d in drafts:
        key = (d.policy_class, d.target, d.line, d.var)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def compare_with_handwritten(drafts: list[DraftAnnotation], handwritten_py: str) -> dict:
    
    import re

    HAND_MAP = {
        "coupon_single_use": "single_use",
        "order_owner_read": "owner",
        "order_owner_pay": "owner",
        "pay_full_amount": "pay_full",
        "ship_requires_paid": "requires_state",
        "admin_required": "role",
    }
    hand = {HAND_MAP[name] for name in re.findall(r"ANOTA_POLICY:(\w+)", handwritten_py)
            if name in HAND_MAP}
    got = {d.policy_class for d in drafts}
    tp = len(hand & got)
    return {
        "handwritten_classes": sorted(hand),
        "drafted_classes": sorted(got),
        "recall": tp / len(hand) if hand else 1.0,
        "extra_drafted": sorted(got - hand),
    }
