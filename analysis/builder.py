from __future__ import annotations
import networkx as nx
from stateforge.core.model import AppModel
_AUTH_ATOM = "Session.authed_as=<authed>"
def _atom(var: str, value) -> str:
    if var == "Session.authed_as":
        return _AUTH_ATOM
    return f"{var}={value}"


def _pre_atom(var: str, op: str, value: str | None) -> str | None:
    
    if var == "Session.authed_as":
        return _AUTH_ATOM
    if op in ("eq", "ne", "in"):
        return _atom(var, value) if value else None
    if op == "truthy":
        return _atom(var, "True")
    if op == "falsy":
        return _atom(var, "False")
    return None


def build_sstg(model: AppModel) -> nx.MultiDiGraph:
    g: nx.MultiDiGraph = nx.MultiDiGraph()
    sv_by_var = {sv.var: sv for sv in model.state_vars}

    def add_state(atom: str, var: str, value):
        if atom not in g:
            sv = sv_by_var.get(var)
            g.add_node(
                atom,
                kind="state",
                var=var,
                value=str(value),
                security_relevant=bool(sv and sv.security_relevant),
                label=(sv.label if sv else None),
            )

    for ep in model.endpoints:
        action = f"{ep.methods[0] if ep.methods else 'GET'} {ep.route}"
        g.add_node(action, kind="action", func=ep.func, file=ep.file, line=ep.line)
        for pre in ep.preconditions:
            atom = _pre_atom(pre.var, pre.op, pre.value)
            if atom:
                add_state(atom, pre.var, pre.value or ("<authed>" if pre.var == "Session.authed_as" else "True"))
                g.add_edge(action, atom, kind="requires", op=pre.op)
        for eff in ep.effects:
            value = eff.value if eff.value is not None else "*"
            atom = _atom(eff.var, value)
            add_state(atom, eff.var, value)
            g.add_edge(action, atom, kind="produces", op=eff.op, key=eff.key)

    
    atoms_by_var: dict[str, list[str]] = {}
    for n, d in g.nodes(data=True):
        if d.get("kind") == "state":
            atoms_by_var.setdefault(d["var"], []).append(n)
    inv_by_var = {inv.var: inv for inv in model.invariants}
    for var, atoms in atoms_by_var.items():
        inv = inv_by_var.get(var)
        if inv is None or len(atoms) < 2:
            continue
        legal = {tuple(t) for t in inv.legal_transitions}
        for a in atoms:
            va = a.split("=", 1)[1]
            for b in atoms:
                vb = b.split("=", 1)[1]
                if a == b:
                    continue
                is_legal = (va, vb) in legal
                if var == "Coupon.used" or inv.one_way:
                    
                    is_legal = (va in ("False", "0", "*")) and vb in ("True", "1", "*")
                g.add_edge(a, b, kind="invariant", legal=is_legal)
    return g
