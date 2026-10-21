from __future__ import annotations
from stateforge.core.model import StateVar
_DIRECT_IN: set[str] = {"authn", "authz", "ownership", "money", "single_use"}


def select(state_vars: list[StateVar]) -> list[StateVar]:
    for sv in state_vars:
        if sv.label in _DIRECT_IN:
            sv.security_relevant = True
            if not sv.rationale.startswith("[select]"):
                sv.rationale += " [select] 固定映射直入"
        elif sv.label == "workflow":
            has_domain = bool(sv.domain) and len(sv.domain) >= 2
            sv.security_relevant = has_domain
            sv.rationale += (
                " [select] workflow 需 domain≥2:" + ("满足" if has_domain else "不满足")
            )
        else:
            sv.security_relevant = False
            sv.rationale += " [select] irrelevant 出局"
    return state_vars
