
from __future__ import annotations

import ast
from pathlib import Path

from stateforge.state.semantic_model import StateVariable, StateSource


class SessionProvenance:

    def __init__(self):
        self.aliases: dict[str, StateVariable] = {}

    def analyze(self, fn_node: ast.FunctionDef) -> None:
        for node in ast.walk(fn_node):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (node.targets if isinstance(node, ast.Assign)
                           else [node.target])
                names = [t.id for t in targets if isinstance(t, ast.Name)]
                if not names:
                    continue
                sv = self._resolve_expr(node.value)
                if sv is not None:
                    for name in names:
                        self.aliases[name] = sv
                elif isinstance(node.value, ast.Name):
                    src = node.value.id
                    if src in self.aliases:
                        for name in names:
                            self.aliases[name] = self.aliases[src]

    def _resolve_expr(self, expr: ast.expr) -> StateVariable | None:
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute):
            obj = expr.func.value
            method = expr.func.attr
            if isinstance(obj, ast.Name) and obj.id == "session" and method == "get":
                if expr.args and isinstance(expr.args[0], ast.Constant):
                    return StateVariable(StateSource.SESSION,
                                       str(expr.args[0].value))
        if isinstance(expr, ast.Subscript):
            if isinstance(expr.value, ast.Name) and expr.value.id == "session":
                if isinstance(expr.slice, ast.Constant):
                    return StateVariable(StateSource.SESSION,
                                       str(expr.slice.value))
        return None

    def lookup(self, var_name: str) -> StateVariable | None:
        return self.aliases.get(var_name)
