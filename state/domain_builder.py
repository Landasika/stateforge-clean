
from __future__ import annotations

from stateforge.state.semantic_model import (
    StateVariable, StatePredicate, PredicateOp)


class VarDomain:

    def __init__(self, variable: StateVariable):
        self.variable = variable
        self.rules: list[tuple[str, StatePredicate]] = []  
        self._ensure_other()

    def add(self, name: str, pred: StatePredicate) -> None:
        self.rules.append((name, pred))
        self._ensure_other()

    def _ensure_other(self) -> None:
        if not any(n == "OTHER" for n, _ in self.rules):
            self.rules.append(("OTHER", None))

    def abstract(self, concrete) -> str:
        from stateforge.state.semantic_model import _eval
        for name, pred in self.rules:
            if pred is not None and _eval(pred, concrete):
                return name
        return "OTHER"

    def to_dict(self) -> dict:
        return {
            "variable": self.variable.canonical,
            "rules": [{"name": n, "pred": p.to_dict() if p else None}
                      for n, p in self.rules],
        }


def build_domains(predicates: list[StatePredicate]) -> dict[str, VarDomain]:
    domains: dict[str, VarDomain] = {}

    for pred in predicates:
        var = pred.variable
        key = var.canonical
        if key not in domains:
            domains[key] = VarDomain(var)

        if pred.op == PredicateOp.EQ:
            name = f"EQ({pred.value})"
        elif pred.op == PredicateOp.IS_NONE:
            name = "NONE"
        elif pred.op == PredicateOp.IS_NOT_NONE:
            name = "NOT_NONE"
        elif pred.op in (PredicateOp.GE, PredicateOp.GT):
            name = f">={pred.value}" if pred.op == PredicateOp.GE else f">{pred.value}"
        else:
            name = f"{pred.op.value}({pred.value})"

        if not any(n == name for n, _ in domains[key].rules):
            domains[key].add(name, pred)

    return domains
