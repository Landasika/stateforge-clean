from __future__ import annotations
import ast
from dataclasses import dataclass
from pathlib import Path
from stateforge.core.ir import ProgramIR
from stateforge.solving.input_provenance import (
    InputSource, _extract, _mentions_request, _parse_chain, _test_at)




def resolve_cross_function(ir: ProgramIR, app_path: Path,
                           callee_function: str,
                           param_name: str) -> InputSource | None:
    
    
    callee_entry = None
    for b in ir.blocks.values():
        if b.function == callee_function and b.kind == "entry":
            callee_entry = b.id
            break
    if not callee_entry:
        return None
    callers: list[tuple[str, int]] = []      
    for e in ir.edges:
        if e.kind == "call" and e.dst == callee_entry:
            caller_block = ir.blocks.get(e.src)
            if caller_block:
                callers.append((caller_block.function,
                                e.callsite_line or 0))
    if not callers:
        return None

    
    try:
        tree = ast.parse(Path(app_path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None

    for caller_fn, callsite_line in callers[:3]:     
        fn_node = _find_function(tree, caller_fn)
        if fn_node is None:
            continue
        arg_expr = _find_call_arg(tree, fn_node, callee_function,
                                  param_name, callsite_line)
        if arg_expr is None:
            continue
        
        if isinstance(arg_expr, ast.Name):
            arg_expr = _resolve_var_in_fn(fn_node, arg_expr.id)
            if arg_expr is None:
                continue
        
        source = _expr_to_source(arg_expr)
        if source:
            source.var = param_name
            return source
    return None

def _resolve_var_in_fn(fn: ast.FunctionDef, var: str) -> ast.expr | None:
    
    result = None
    for stmt in ast.walk(fn):
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == var:
                    result = stmt.value
        elif isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name) and stmt.target.id == var:
                result = stmt.value
    return result

def _find_function(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == name:
            return node
    return None


def _find_call_arg(tree: ast.Module, fn: ast.FunctionDef, callee: str,
                   param: str, near_line: int) -> ast.expr | None:
    
    
    callee_fn = _find_function(tree, callee)
    if callee_fn is None:
        return None
    param_names = [a.arg for a in callee_fn.args.args]
    if param not in param_names:
        return None
    param_index = param_names.index(param)

    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        callee_name = None
        if isinstance(func, ast.Name):
            callee_name = func.id
        elif isinstance(func, ast.Attribute):
            callee_name = func.attr
        if callee_name != callee:
            continue
        
        for kw in node.keywords:
            if kw.arg == param:
                return kw.value
        
        if param_index < len(node.args):
            return node.args[param_index]
    return None


def _expr_to_source(expr) -> InputSource | None:
    
    if isinstance(expr, list):
        for e in expr:
            r = _expr_to_source(e)
            if r:
                return r
        return None
    chain, base = _parse_chain(expr)
    hit = _extract(base)
    if hit is None or hit[0] == "AMBIGUOUS":
        return None
    kind, key = hit
    transform = "->".join(chain) if chain else "identity"
    return InputSource(kind, key, transform, "", transforms=tuple(chain))





@dataclass
class ValueMatch:
    kind: str                 
    key: str
    field_value: object       
    guard_value: object       
    transform: str            
    confidence: float         

def correlate_values(guard_operands: list[object],
                     seed: dict) -> list[ValueMatch]:
    
    matches = []
    sections = {"QUERY": "query", "FORM": "form", "JSON": "json",
                "HEADER": "header", "COOKIE": "cookie"}
    for kind, section in sections.items():
        fields = seed.get(section, {})
        if not isinstance(fields, dict):
            continue
        for key, field_val in fields.items():
            for operand in guard_operands:
                if operand is None:
                    continue
                if _values_equal(field_val, operand):
                    matches.append(ValueMatch(
                        kind, key, field_val, operand, "identity", 1.0))
                    continue
                
                if isinstance(operand, (int, float)) \
                        and isinstance(field_val, str):
                    try:
                        if float(field_val) == float(operand):
                            matches.append(ValueMatch(
                                kind, key, field_val, operand, "int", 0.8))
                    except ValueError:
                        pass
                
                if isinstance(operand, str) and isinstance(field_val, str):
                    if field_val.strip() == operand:
                        matches.append(ValueMatch(
                            kind, key, field_val, operand, "strip", 0.8))
    return matches

def _values_equal(a, b) -> bool:
    if type(a) is type(b):
        return a == b
    return False




def resolve_enhanced(ir: ProgramIR, app_path: Path,
                     function_name: str, guard_lineno: int,
                     guard_operands: list[object] | None = None,
                     seed: dict | None = None) -> InputSource:
    
    
    from stateforge.solving.input_provenance import (
        resolve_operand_source)
    result = resolve_operand_source(app_path, function_name, guard_lineno)
    if result.status == "ok":
        return result

    
    tree = ast.parse(Path(app_path).read_text(encoding="utf-8"))
    fn = _find_function(tree, function_name)
    if fn:
        param_names = [a.arg for a in fn.args.args]
        test = _test_at(fn, guard_lineno)
        if test and isinstance(test, ast.Compare):
            for side in (test.left, test.comparators[0] if test.comparators else None):
                if isinstance(side, ast.Name) and side.id in param_names:
                    cross = resolve_cross_function(ir, app_path,
                                                   function_name, side.id)
                    if cross:
                        cross.status = "ok"
                        cross.confidence = 0.8     
                        return cross
    if guard_operands and seed:
        matches = correlate_values(guard_operands, seed)
        if matches:
            best = sorted(matches, key=lambda m: -m.confidence)[0]
            return InputSource(
                best.kind, best.key,
                best.transform, "",
                status="ok", confidence=0.6)    

    return result       
