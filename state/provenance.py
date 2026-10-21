from __future__ import annotations
import ast
import re
from dataclasses import dataclass
from pathlib import Path
from stateforge.state.relational import VarProvenance
_SELECT_RE = re.compile(r"^\s*SELECT\b.+?\bFROM\s+(`?\w+`?)",
                        re.IGNORECASE | re.DOTALL)
_WHERE_KEY_RE = re.compile(r"\bWHERE\s+(`?\w+`?)\s*=\s*\?",
                           re.IGNORECASE)
_ROUTE_PARAM_RE = re.compile(r"<(?:int:|string:|path:)?(\w+)>")
_AUTH_HINTS = ("headers", "cookies", "Authorization", "authorization")

@dataclass(frozen=True)
class _CalleeProfile:
    

    table: str | None
    where_key: str | None
    sql: str
    auth: bool
    returns_nonconst: bool


def _profile(fn: ast.FunctionDef, funcs: dict[str, ast.FunctionDef],
             depth: int = 0) -> _CalleeProfile | None:
    
    table: str | None = None
    where_key: str | None = None
    sql = ""
    auth = False
    returns_nonconst = False
    for node in ast.walk(fn):
        
        if isinstance(node, ast.Attribute) and node.attr in _AUTH_HINTS:
            auth = True
        
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "execute" and node.args):
            sql_const = node.args[0]
            if isinstance(sql_const, ast.Constant) \
                    and isinstance(sql_const.value, str):
                m = _SELECT_RE.match(sql_const.value)
                if m:
                    table = m.group(1).strip("`")
                    sql = sql_const.value
                    mk = _WHERE_KEY_RE.search(sql_const.value)
                    if mk:
                        where_key = mk.group(1).strip("`")
        if isinstance(node, ast.Return) and node.value is not None:
            if not isinstance(node.value, ast.Constant):
                returns_nonconst = True
    
    if table is None and depth < 1:
        inner: _CalleeProfile | None = None
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in funcs
                    and node.func.id != fn.name):
                prof = _profile(funcs[node.func.id], funcs, depth + 1)
                if prof is not None and prof.table is not None:
                    if inner is not None and inner.table != prof.table:
                        return None          
                    inner = prof
        if inner is not None:
            return _CalleeProfile(table=inner.table, where_key=inner.where_key,
                                  sql=inner.sql, auth=auth or inner.auth,
                                  returns_nonconst=True)
    if table is None and not auth:
        return None
    return _CalleeProfile(table=table, where_key=where_key, sql=sql,
                          auth=auth, returns_nonconst=returns_nonconst)


def _store_table_node(node) -> str | None:
    
    if (isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id in ("_DB", "DB", "db")
            and isinstance(node.slice, ast.Constant)):
        return str(node.slice.value)
    return None


class ProvenanceIndex:
    

    def __init__(self, funcs: dict[str, ast.FunctionDef],
                 routes: dict[str, set[str]],
                 vars_: dict[tuple[str, str], VarProvenance],
                 assigned: dict[str, set[str]],
                 params: dict[str, set[str]]):
        self._funcs = funcs
        self._routes = routes
        self._vars = vars_
        self._assigned = assigned
        self._params = params

    def lookup(self, fn_name: str, local_var: str) -> VarProvenance | None:
        return self._vars.get((fn_name, local_var))

    def var_kind(self, fn_name: str, name: str) -> str:
        if name in self._routes.get(fn_name, ()):
            return "route-param"
        if name in self._params.get(fn_name, ()):
            return "param"
        if name in self._assigned.get(fn_name, ()):
            return "local"
        return "config"

    def is_local(self, fn_name: str, name: str) -> bool:
        return name in self._assigned.get(fn_name, ())


def analyze_provenance(source_file: str | Path) -> ProvenanceIndex:
    
    path = Path(source_file)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return ProvenanceIndex({}, {}, {}, {}, {})

    funcs: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = node          

    
    routes: dict[str, set[str]] = {}
    for name, fn in funcs.items():
        params: set[str] = set()
        for dec in fn.decorator_list:
            targets = [dec] if isinstance(dec, ast.Call) else []
            if isinstance(dec, ast.Call):
                targets = dec.args
            for arg in targets:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    params.update(_ROUTE_PARAM_RE.findall(arg.value))
        if params:
            routes[name] = params

    vars_: dict[tuple[str, str], VarProvenance] = {}
    assigned: dict[str, set[str]] = {}
    params_map: dict[str, set[str]] = {
        n: {a.arg for a in f.args.args} for n, f in funcs.items()}
    for fn_name, fn in funcs.items():
        local_assigned: set[str] = set()
        for node in ast.walk(fn):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                names = ([target.id] if isinstance(target, ast.Name)
                         else [t.id for t in target.elts
                               if isinstance(t, ast.Name)] if isinstance(target, ast.Tuple)
                         else [])
                local_assigned.update(names)
                if not names:
                    continue
                head = names[0]             
                origin: tuple[str, ...] = ()
                table = None
                key_param = None
                auth = False
                line = node.lineno
                src = str(path)

                value = node.value
                
                if isinstance(value, ast.Call) \
                        and isinstance(value.func, ast.Name) \
                        and value.func.id in funcs \
                        and value.func.id != fn_name:
                    callee = funcs[value.func.id]
                    prof = _profile(callee, funcs)
                    if prof is not None and prof.returns_nonconst:
                        table = prof.table
                        auth = prof.auth
                        args_repr = ", ".join(ast.unparse(a) for a in value.args)
                        origin = (f"call:{value.func.id}({args_repr})",
                                  *(f"sql:{prof.sql[:60]}" if prof.sql else "",),
                                  *((f"key:{prof.where_key}",)
                                    if prof.where_key else ()))
                        
                        if value.args and isinstance(value.args[0], ast.Name):
                            key_param = value.args[0].id
                        elif prof.where_key:
                            key_param = prof.where_key
                
                elif (isinstance(value, ast.Subscript)
                      and (t := _store_table_node(value.value)) is not None):
                    table = t
                    origin = (f"store:_DB[{t!r}]",)
                    if isinstance(value.slice, ast.Name):
                        key_param = value.slice.id

                if origin:                   
                    vars_[(fn_name, head)] = VarProvenance(
                        var=f"?{head}", table=table, key_param=key_param,
                        origin=origin, auth_subject=auth,
                        source_file=src, source_line=line)
        assigned[fn_name] = local_assigned

    return ProvenanceIndex(funcs, routes, vars_, assigned, params_map)
