from __future__ import annotations
from dataclasses import dataclass
from stateforge.solving.branch_observer import BranchObservation
_NUMERIC = (int, float)
_FLIP = {"Eq": "NotEq", "NotEq": "Eq", "Lt": "GtE", "GtE": "Lt",
         "LtE": "Gt", "Gt": "LtE"}


def _numeric_distance(op: str, lhs, rhs) -> int | float:
    if op == "Eq":
        
        if isinstance(lhs, str) or isinstance(rhs, str):
            return 0 if lhs == rhs else 1
        return abs(lhs - rhs)
    if op == "NotEq":
        return 0 if lhs != rhs else 1
    if op == "Lt":
        return max(0, lhs - rhs + 1)
    if op == "LtE":
        return max(0, lhs - rhs)
    if op == "Gt":
        return max(0, rhs - lhs + 1)
    if op == "GtE":
        return max(0, rhs - lhs)
    raise ValueError(op)


@dataclass(frozen=True)
class BranchDistance:
    guard_id: str
    raw_distance: float | None
    normalized_distance: float | None
    satisfied: bool
    status: str = "ok"            


def branch_distance(obs: BranchObservation, desired_polarity: str
                    ) -> BranchDistance:
    
    want = desired_polarity == "true"
    op = obs.op
    if op == "truthy":
        raw = 0 if bool(obs.lhs) == want else 1
    elif op == "not_truthy":
        raw = 0 if (not bool(obs.lhs)) == want else 1
    elif isinstance(obs.lhs, _NUMERIC) and isinstance(obs.rhs, _NUMERIC):
        effective_op = op if want else _FLIP[op]
        raw = _numeric_distance(effective_op, obs.lhs, obs.rhs)
    elif op in ("Eq", "NotEq") and isinstance(obs.lhs, str) \
            and isinstance(obs.rhs, str):
        effective_op = op if want else _FLIP[op]
        raw = _numeric_distance(effective_op, obs.lhs, obs.rhs)
    else:
        return BranchDistance(obs.guard_id, None, None,
                              satisfied=obs.actual == want,
                              status="OPERAND_UNAVAILABLE")
    return BranchDistance(obs.guard_id, raw, raw / (raw + 1),
                          satisfied=(raw == 0))
