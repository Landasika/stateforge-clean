from __future__ import annotations
import ast
from dataclasses import dataclass
from pathlib import Path

KIND_ATTR = {"args": "QUERY", "form": "FORM", "json": "JSON",
             "headers": "HEADER", "cookies": "COOKIE"}


_AMBIGUOUS_ATTRS = {"values", "data", "query_string"}

TRANSFORMS = ("int", "float", "str", "strip", "lower", "upper")
@dataclass
class InputSource:
    kind: str                    
    key: str
    transform: str               
    var: str                     
    status: str = "ok"           
    confidence: float = 1.0
    transforms: tuple = ()       
def apply_transforms(raw, chain):
    
    for t in chain:
        if t == "int":
            raw = int(raw)
        elif t == "float":
            raw = float(raw)
        elif t == "str":
            raw = str(raw)
        elif t == "strip":
            raw = raw.strip()
        elif t == "lower":
            raw = raw.lower()
        elif t == "upper":
            raw = raw.upper()
        else:
            raise ValueError(t)
    return raw


def _match_source(expr: ast.expr) -> tuple[str, str] | None:
    
    inner = expr
    if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) \
            and inner.func.attr == "get" and len(inner.args) == 1 \
            and isinstance(inner.args[0], ast.Constant):
        inner = inner.func.value
        key = None
        
        return None  
    return None


def _extract(expr: ast.expr) -> tuple[str, str] | None:
    if isinstance(expr, ast.Subscript) and isinstance(expr.value, ast.Attribute):
        attr = expr.value
        if isinstance(attr.value, ast.Name) and attr.value.id == "request" \
                and isinstance(expr.slice, ast.Constant):
            if attr.attr in KIND_ATTR:
                return KIND_ATTR[attr.attr], str(expr.slice.value)
            if attr.attr in _AMBIGUOUS_ATTRS:
                return "AMBIGUOUS", attr.attr
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) \
            and expr.func.attr == "get" \
            and isinstance(expr.func.value, ast.Attribute) \
            and isinstance(expr.func.value.value, ast.Name) \
            and expr.func.value.value.id == "request" \
            and expr.func.value.attr in KIND_ATTR \
            and 1 <= len(expr.args) <= 2 and isinstance(expr.args[0], ast.Constant):
        return KIND_ATTR[expr.func.value.attr], str(expr.args[0].value)
    return None


def _mentions_request(value: ast.expr) -> bool:
    
    for node in ast.walk(value):
        if isinstance(node, ast.Attribute) and node.attr in KIND_ATTR:
            if isinstance(node.value, ast.Name) and node.value.id == "request":
                return True
    return False


def _parse_chain(value: ast.expr) -> tuple[list[str], ast.expr]:
    
    chain: list[str] = []
    expr = value
    while True:
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) \
                and expr.func.id in ("int", "float", "str") and len(expr.args) == 1:
            chain.append(expr.func.id)
            expr = expr.args[0]
        elif isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) \
                and expr.func.attr in ("strip", "lower", "upper") \
                and not expr.args:
            chain.append(expr.func.attr)
            expr = expr.func.value
        else:
            return chain, expr


def _assign_source(stmt: ast.stmt) -> InputSource | None:
    
    if not isinstance(stmt, (ast.Assign, ast.AnnAssign)):
        return None
    targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
    names = [t.id for t in targets if isinstance(t, ast.Name)]
    if not names:
        return None
    chain, base = _parse_chain(stmt.value)
    hit = _extract(base)
    if hit is None or hit[0] == "AMBIGUOUS":
        if _mentions_request(stmt.value):
            status = ("SOURCE_AMBIGUOUS" if (hit and hit[0] == "AMBIGUOUS")
                      else "UNRESOLVED_TRANSFORM")
            return InputSource("", "", "UNRESOLVED", names[0],
                               status=status, confidence=0.0)
        return None                              
    kind, key = hit
    transform = "->".join(chain) if chain else "identity"
    return InputSource(kind, key, transform, names[0],
                       transforms=tuple(chain))

def _assign_targets(stmt):
    if isinstance(stmt, ast.Assign):
        return [t.id for t in stmt.targets if isinstance(t, ast.Name)]
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        return [stmt.target.id]
    return []


def _scan_function_before(fn: ast.FunctionDef, guard_line: int
                          ) -> dict[str, InputSource]:
    
    direct: list[tuple[int, str, InputSource]] = []
    ambiguous: set[str] = set()

    def visit(stmts, in_branch: bool):
        for s in stmts:
            if isinstance(s, (ast.Assign, ast.AnnAssign)):
                src = _assign_source(s)
                names = _assign_targets(s)
                if src is not None:
                    for n in names:
                        if in_branch:
                            ambiguous.add(n)
                        else:
                            direct.append((s.lineno, n, src))
                elif in_branch and _mentions_request(s.value):
                    ambiguous.update(names)
            elif not isinstance(s, (ast.If, ast.While, ast.For,
                                    ast.AsyncFor, ast.Try)):
                pass
            for field in ("body", "orelse", "finalbody", "handlers"):
                for child in getattr(s, field, []) or []:
                    if isinstance(child, ast.stmt):
                        visit([child], in_branch=True)
                    elif isinstance(child, ast.ExceptHandler):
                        visit(child.body, in_branch=True)

    visit(fn.body, in_branch=False)
    env: dict[str, InputSource] = {}
    for lineno, name, src in sorted(direct, key=lambda t: t[0]):
        if lineno >= guard_line:                   
            continue
        if name in ambiguous:
            continue
        env[name] = src
    for name in ambiguous:
        if name not in env:
            env[name] = InputSource("", "", "", name,
                                    status="SOURCE_AMBIGUOUS", confidence=0.0)
    return env


def resolve_operand_source(app_path: str | Path, function: str,
                           guard_lineno: int) -> InputSource:
    
    tree = ast.parse(Path(app_path).read_text(encoding="utf-8"))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == function), None)
    if fn is None:
        return InputSource("", "", "", "", status="SOURCE_UNKNOWN", confidence=0.0)
    env = _scan_function_before(fn, guard_lineno)
    test = _test_at(fn, guard_lineno)
    if test is None or not isinstance(test, ast.Compare) \
            or len(test.ops) != 1:
        return InputSource("", "", "", "", status="SOURCE_UNKNOWN", confidence=0.0)
    for side in (test.left, test.comparators[0]):
        if isinstance(side, ast.Name):
            hit = env.get(side.id)
            if hit is not None:
                return hit
            
    return InputSource("", "", "", "", status="SOURCE_UNKNOWN", confidence=0.0)


def _test_at(fn: ast.FunctionDef, lineno: int) -> ast.expr | None:
    for stmt in ast.walk(fn):
        if isinstance(stmt, (ast.If, ast.While)) \
                and getattr(stmt, "test", None) is not None \
                and stmt.test.lineno == lineno:
            return stmt.test
    return None
