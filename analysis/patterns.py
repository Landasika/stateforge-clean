from __future__ import annotations
import ast
import re
from collections import defaultdict
from stateforge.core.model import (
    CandidateSource,
    Effect,
    Endpoint,
    Guard,
    HttpMethod,
    Param,
    Precondition,
    Sink,
    StateCandidate,
)




def _lit(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _subscript_parts(node) -> tuple[str, str] | None:
    
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        base = node.value
        if isinstance(base, ast.Name):
            return base.id, str(node.slice.value)
        if isinstance(base, ast.Call):  
            return None
    return None


def _is_guard_return_body(body: list[ast.stmt]) -> bool:
    
    if not body:
        return False
    first = body[0]
    if isinstance(first, (ast.Return, ast.Raise)):
        return True
    return (isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
            and isinstance(first.value.func, ast.Name)
            and first.value.func.id == "abort")


def _guard_return_test_ids(func: ast.AST) -> frozenset[int]:
    
    ids: set[int] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.If) and _is_guard_return_body(node.body):
            ids.update(id(n) for n in ast.walk(node.test))
    return frozenset(ids)


_SINGULAR = {"orders": "Order", "coupons": "Coupon", "users": "User", "books": "Book"}


def entity_of_table(table: str) -> str:
    if table in _SINGULAR:
        return _SINGULAR[table]
    if table.endswith("s"):
        return table[:-1].capitalize()
    return table.capitalize()
_UPDATE_RE = re.compile(r"UPDATE\s+(\w+)\s+SET\s+(.+?)\s+WHERE", re.IGNORECASE | re.DOTALL)
_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+(\w+)\s*\(([^)]*)\)\s*VALUES\s*\(([^)]*)\)", re.IGNORECASE
)


def parse_sql_effects(sql: str) -> list[tuple[str, str, str | None]]:
    
    out: list[tuple[str, str, str | None]] = []
    m = _UPDATE_RE.search(sql)
    if m:
        table, sets = m.group(1), m.group(2)
        for piece in sets.split(","):
            if "=" not in piece:
                continue
            col, val = piece.split("=", 1)
            col, val = col.strip(), val.strip().strip("'\"")
            if val == "?":
                continue
            out.append((f"{entity_of_table(table)}.{col}", "set", val))
        return out
    m = _INSERT_RE.search(sql)
    if m:
        table, cols, vals = m.group(1), m.group(2), m.group(3)
        cols = [c.strip() for c in cols.split(",")]
        vals = [v.strip() for v in vals.split(",")]
        for col, val in zip(cols, vals):
            if col in ("id",):
                continue
            if val.startswith(("'", '"')):
                out.append((f"{entity_of_table(table)}.{col}", "set", val.strip("'\"")))
            elif re.fullmatch(r"\d+", val):
                out.append((f"{entity_of_table(table)}.{col}", "set", val))
        return out
    return out





class EndpointExtractor(ast.NodeVisitor):
    

    def __init__(self, file: str, config_flags: dict[str, int] | None = None):
        self.file = file
        self.endpoints: list[Endpoint] = []
        self.candidates: list[StateCandidate] = []
        self.config_flags: dict[str, int] = config_flags if config_flags is not None else {}
        self._funcs: dict[str, ast.FunctionDef] = {}
        self._classes: dict[str, ast.ClassDef] = {}

    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._funcs.setdefault(node.name, node)
        for route, methods in _route_of(node):
            self._extract_endpoint(node, route, methods)
        self.generic_visit(node)
    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._classes.setdefault(node.name, node)
        self.generic_visit(node)
    def visit_Call(self, call: ast.Call) -> None:
        name = _any_name(call)
        if name in ("register_view", "add_url_rule"):
            kws = {k.arg: k.value for k in call.keywords if k.arg}
            routes = _literal_list(kws.get("routes")) or (
                [_lit(call.args[1])] if name == "add_url_rule" and len(call.args) > 1
                and _lit(call.args[1]) else [])
            vf = kws.get("view_func") or (call.args[2] if len(call.args) > 2 else None)
            targets = self._view_targets(vf)
            for route in routes:
                for methods, fdef in targets:
                    ep = Endpoint(func=fdef.name if fdef else str(route),
                                  route=route, methods=methods,
                                  file=self.file,
                                  line=(fdef.lineno if fdef else getattr(call, "lineno", 0)),
                                  params=_path_params(route))
                    if fdef is not None:
                        self._extract_endpoint_into(fdef, route, methods, ep)
                    self.endpoints.append(ep)
        self.generic_visit(call)

    def _view_targets(self, vf) -> list[tuple[list[HttpMethod], ast.FunctionDef | None]]:
        
        if vf is None:
            return [(["GET"], None)]  
        cls_name = None
        if isinstance(vf, ast.Call) and isinstance(vf.func, ast.Attribute) \
                and vf.func.attr == "as_view" and isinstance(vf.func.value, ast.Name):
            cls_name = vf.func.value.id
        elif isinstance(vf, ast.Name):
            fname = vf.id
            if fname in self._funcs:
                return [(["GET"], self._funcs[fname])]  
        if cls_name and cls_name in self._classes:
            out = []
            for m in ("get", "post", "put", "delete"):
                for sub in ast.walk(self._classes[cls_name]):
                    if isinstance(sub, ast.FunctionDef) and sub.name == m:
                        out.append(([m.upper()], sub))  
            return out or [(["GET"], None)]  
        return [(["GET"], None)]  

    
    def visit_Assign(self, node: ast.Assign) -> None:
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
            and _is_os_getenv_int(node.value)
        ):
            name = node.targets[0].id
            self.config_flags[name.upper()] = _getenv_default(node.value)
        self.generic_visit(node)

    
    def _extract_endpoint(self, func: ast.FunctionDef, route: str, methods: list[HttpMethod]) -> None:
        ep = Endpoint(
            func=func.name, route=route, methods=methods,
            file=self.file, line=func.lineno,
            params=_path_params(route),
        )
        self._extract_endpoint_into(func, route, methods, ep)
        self.endpoints.append(ep)

    def _extract_endpoint_into(
        self, func: ast.FunctionDef, route: str, methods: list[HttpMethod], ep: Endpoint
    ) -> _EpEnv:
        env = _EpEnv(self.file, ep, self.candidates, self.config_flags,
                     _guard_return_test_ids(func))
        for stmt in ast.walk(func):
            env.visit_node(stmt)
        
        ep.effects = _dedup_by(ep.effects, key=lambda e: (e.var, e.op, e.value, e.key))
        ep.preconditions = _dedup_by(
            ep.preconditions, key=lambda p: (p.var, p.op, p.value, p.key)
        )
        return env


class _EpEnv:
    
    def __init__(self, file, ep: Endpoint, candidates: list[StateCandidate], flags: dict,
                 guard_return_ids: frozenset[int] = frozenset()):
        self.file, self.ep, self.cands, self.flags = file, ep, candidates, flags
        self.guard_ids = guard_return_ids
        self.json_bodies: set[str] = set()  
        self._cand_ops: dict[str, set] = defaultdict(set)
        self._cand_evidence: dict[str, list] = defaultdict(list)

    def visit_node(self, node) -> None:
        if isinstance(node, ast.Call):
            self._call(node)
        elif isinstance(node, ast.Compare):
            self._compare(node)
        elif isinstance(node, ast.If):
            self._if(node)
        elif isinstance(node, ast.Assign):
            self._assign(node)
        elif isinstance(node, ast.Return):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    self._jsonify(sub)

    
    def _call(self, call: ast.Call) -> None:
        name = _call_name(call)
        bare = _bare_name(call)
        if name.endswith(".execute"):
            sql = _lit(call.args[0]) if call.args else None
            if sql:
                for var, op, val in parse_sql_effects(sql):
                    self.ep.effects.append(Effect(
                        var=var, op=op, value=val, file=self.file,
                        line=_line(call, sql),
                    ))
                    self._cand(var, "write", f"execute({sql[:60]}...)", "db_field")
            elif call.args and _is_concat(call.args[0]):
                self.ep.sinks.append(Sink(
                    kind="sql_build", file=self.file, line=getattr(call, "lineno", 0),
                    snippet=ast.dump(call.args[0])[:120],
                ))
        elif bare == "jsonify":
            self._jsonify(call)
        elif name.endswith(".get") and isinstance(call.func, ast.Attribute) and (
            (isinstance(call.func.value, ast.Name) and call.func.value.id in self.json_bodies)
            or _is_inline_json(call.func.value)
        ):
            if call.args and isinstance(call.args[0], ast.Constant):
                self.ep.params.append(Param(name=str(call.args[0].value), location="json"))

    def _jsonify(self, call: ast.Call) -> None:
        if _any_name(call) != "jsonify" or not call.args:
            return
        arg = call.args[0]
        keys: list[str] = []
        if isinstance(arg, ast.Dict):
            keys = [k.value for k in arg.keys if isinstance(k, ast.Constant)]
        elif isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            try:
                import json
                keys = list(json.loads(arg.value).keys())
            except Exception:
                pass
        self.ep.observes.extend(k for k in keys if k not in self.ep.observes)

    
    def _compare(self, comp: ast.Compare) -> None:
        left, right = comp.left, comp.comparators[0] if len(comp.comparators) == 1 else None
        if right is None:
            return
        sub = _subscript_parts(left) or _subscript_parts(right)
        litv = _lit(right) or _lit(left)
        if sub and litv:
            row, attr = sub
            var = _normalize_var(row, attr)
            op = {ast.Eq: "eq", ast.NotEq: "ne", ast.In: "in"}.get(type(comp.ops[0]))
            if op:
                
                
                
                if op != "ne" or id(comp) in self.guard_ids:
                    self.ep.preconditions.append(Precondition(
                        var=var, op=op, value=litv, file=self.file,
                        line=getattr(comp, "lineno", 0),
                    ))
                self._cand(var, "compare", f'{var} {op} "{litv}"', "condition")
        
        a, b = _subscript_parts(left), _subscript_parts(right)
        if a and b:
            var = _normalize_var(*a)
            self._cand(var, "compare", f'{a[0]}["{a[1]}"] vs {b[0]}["{b[1]}"]', "ownership_binding")
            self.ep.preconditions.append(Precondition(
                var=var, op="eq", key=f'{b[0]}.{b[1]}', file=self.file,
                line=getattr(comp, "lineno", 0),
            ))

    
    def _if(self, node: ast.If) -> None:
        test = node.test
        negated = isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)
        inner = test.operand if negated else test
        if (sub := _subscript_parts(inner)):
            row, attr = sub
            var = _normalize_var(row, attr)
            op = "falsy" if negated else "truthy"
            self.ep.preconditions.append(Precondition(
                var=var, op=op, file=self.file, line=node.lineno,
            ))
            self._cand(var, "compare", f'if {"not " if negated else ""}{row}["{attr}"]', "condition")
        
        for comp in [n for n in ast.walk(node) if isinstance(n, ast.Compare)]:
            self._guard_from_compare(comp, node.lineno)

    def _guard_from_compare(self, comp: ast.Compare, line: int) -> None:
        if not (len(comp.ops) == 1 and isinstance(comp.ops[0], (ast.Eq, ast.NotEq))):
            return
        a = _subscript_parts(comp.left)
        b = _subscript_parts(comp.comparators[0])
        litv = _lit(comp.comparators[0]) or _lit(comp.left)
        ne = isinstance(comp.ops[0], ast.NotEq)
        new_guards: list[Guard] = []
        if a and b:
            (r1, f1), (r2, f2) = a, b
            if f1 == "user_id" or f2 == "user_id" or (f1 == "id" and r2 == "user") or (f2 == "id" and r1 == "user"):
                new_guards.append(Guard(
                    kind="owner", present=True, detail=f"{r1}.{f1} == {r2}.{f2}",
                    file=self.file, line=line,
                ))
            if "role" in (f1, f2) or "admin" in (f1, f2):
                new_guards.append(Guard(
                    kind="role", present=True,
                    detail=f"{r1}.{f1} {'!=' if ne else '=='} {r2}.{f2}",
                    file=self.file, line=line,
                ))
        elif a and litv:  
            r1, f1 = a
            if f1 in ("role", "admin"):
                new_guards.append(Guard(
                    kind="role", present=True, detail=f'{r1}.{f1} {"!=" if ne else "=="} "{litv}"',
                    file=self.file, line=line,
                ))
            elif f1 == "status":
                new_guards.append(Guard(
                    kind="custom", present=True, detail=f'{r1}.status {"==" if ne else "!="} "{litv}"',
                    file=self.file, line=line,
                ))
        for g in new_guards:  
            if (g.kind, g.detail) not in {(x.kind, x.detail) for x in self.ep.guards}:
                self.ep.guards.append(g)

    
    
    
    def _assign(self, node: ast.Assign) -> None:
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            value = node.value
            if isinstance(value, ast.BoolOp):  
                value = value.values[0]
            if isinstance(value, ast.Call) and _call_name(value).endswith(".get_json"):
                self.json_bodies.add(node.targets[0].id)
            
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                self._cand(value.func.id, "write",
                           ast.unparse(node)[:60], "call")
        
        
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Attribute)
            and isinstance(node.targets[0].value, ast.Name)
        ):
            attr_node = node.targets[0]
            var = f"{attr_node.value.id}.{attr_node.attr}"
            self.ep.effects.append(Effect(
                var=var, op="set", file=self.file,
                line=getattr(node, "lineno", 0),
            ))
            self._cand(var, "write", ast.unparse(node)[:60], "db_field")
        
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Subscript)
            and isinstance(node.targets[0].slice, ast.Constant)
            and isinstance(node.targets[0].value, ast.Name)
        ):
            t = node.targets[0]
            var = f"{t.value.id}.{t.slice.value}"
            self.ep.effects.append(Effect(
                var=var, op="set", file=self.file, line=getattr(node, "lineno", 0),
            ))
            self._cand(var, "write", ast.unparse(node)[:60], "session_access")
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id[:1].isupper()
        ):
            entity = node.value.func.id
            for kw in node.value.keywords:
                if kw.arg is None:
                    continue
                value = (
                    str(kw.value.value)
                    if isinstance(kw.value, ast.Constant)
                    else None
                )
                var = f"{entity}.{kw.arg}"
                self.ep.effects.append(Effect(
                    var=var, op="set", value=value,
                    file=self.file, line=getattr(node, "lineno", 0),
                ))
                self._cand(var, "write", ast.unparse(node)[:60], "db_field")

    
    def _cand(self, var: str, op: str, evidence: str, source: CandidateSource) -> None:
        for c in self.cands:
            if c.var == var:
                if op not in c.ops:
                    c.ops.append(op)
                return
        entity, _, attr = var.partition(".")
        self.cands.append(StateCandidate(
            var=var, entity=entity or None, attr=attr or None, ops=[op],
            evidence=evidence, source=source, file=self.file, line=0,
        ))





def _route_of(node: ast.FunctionDef) -> list[tuple[str, list[HttpMethod]]]:
    out = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
            attr = dec.func.attr
            if attr in ("get", "post", "put", "delete", "patch") and dec.args and _lit(dec.args[0]):
                out.append((dec.args[0].value, [attr.upper()]))  
            elif attr == "route" and dec.args and _lit(dec.args[0]):
                methods: list[HttpMethod] = ["GET"]  
                for kw in dec.keywords:
                    if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                        methods = [
                            e.value for e in kw.value.elts  
                            if isinstance(e, ast.Constant)
                        ]
                out.append((dec.args[0].value, methods))
    return out


def _literal_list(node) -> list[str]:
    if isinstance(node, (ast.List, ast.Tuple)):
        return [e.value for e in node.elts if isinstance(e, ast.Constant)
                and isinstance(e.value, str)]
    return []

def _path_params(route: str) -> list[Param]:
    params = []
    for m in re.finditer(r"<(?:int:|string:|path:)?(\w+)>", route):
        params.append(Param(name=m.group(1), location="path", py_type="str"))
    return params


def _call_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Attribute):
        base = f.value.id if isinstance(f.value, ast.Name) else (
            _call_name(f.value) if isinstance(f.value, ast.Call) else ""
        )
        return f"{base}.{f.attr}"
    return f.id if isinstance(f, ast.Name) else ""


def _is_os_getenv_int(call: ast.Call) -> bool:
    f = call.func
    inner = call
    if isinstance(f, ast.Name) and f.id == "int" and call.args:  
        inner_arg = call.args[0]
        if isinstance(inner_arg, ast.Call):
            inner = inner_arg
            f = inner.func
    return (
        isinstance(f, ast.Attribute)
        and f.attr == "getenv"
        and isinstance(f.value, ast.Name)
        and f.value.id == "os"
        and bool(inner.args)
    )


def _getenv_default(call: ast.Call) -> int:
    target = call
    if isinstance(call.func, ast.Name) and call.func.id == "int" and call.args:
        target = call.args[0] if isinstance(call.args[0], ast.Call) else call
    if len(target.args) > 1 and isinstance(target.args[1], ast.Constant):
        try:
            return int(target.args[1].value)
        except (TypeError, ValueError):
            return 0
    for kw in target.keywords:
        if kw.arg == "default" and isinstance(kw.value, ast.Constant):
            try:
                return int(kw.value.value)
            except (TypeError, ValueError):
                return 0
    return 0


def _is_inline_json(node) -> bool:
    
    if isinstance(node, ast.BoolOp):
        return any(_is_inline_json(v) for v in node.values)
    if isinstance(node, ast.Call):
        return _call_name(node).endswith(".get_json")
    return False


_KNOWN_ENTITIES = {"Order", "Coupon", "User", "Book", "Session"}


def _var_entity_known(var: str) -> bool:
    return var.partition(".")[0] in _KNOWN_ENTITIES


def _dedup_by(items: list, key) -> list:
    seen: set = set()
    out = []
    for it in items:
        k = key(it)
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def _bare_name(call: ast.Call) -> str:
    return call.func.id if isinstance(call.func, ast.Name) else ""


def _any_name(call: ast.Call) -> str:
    
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _is_concat(node) -> bool:
    return isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)


def _line(call, sql: str) -> int:
    return getattr(call, "lineno", 0) or 0


_ROW_ENTITY = {
    "order": "Order", "coupon": "Coupon", "user": "User", "book": "Book",
    "newBook": "Book", "order2": "Order", "coupon2": "Coupon", "target": "User",
    "newUser": "User", "found": "User",
}

def _normalize_var(row: str, attr: str) -> str:
    entity = _ROW_ENTITY.get(row)
    if entity is None:
        return f"{row}.{attr}"
    return f"{entity}.{attr}"
