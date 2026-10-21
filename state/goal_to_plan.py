from __future__ import annotations
import ast
from pathlib import Path
from stateforge.analysis.builder import build_sstg
from stateforge.core.model import AppModel, Effect, Endpoint, Precondition
from stateforge.state.extractor import (StateFactCandidate, StateOperation,
                                        _store_table)
from stateforge.state.goal_derivation import StateGoal, derive_state_goal
from stateforge.state.planning.backward import plan_backward
from stateforge.state.planning.goals import GoalSpec
def _fn_ast(source_file: str):
    try:
        return ast.parse(Path(source_file).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _body_vars(tree) -> set[str]:
    
    out: set[str] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "get"
                and node.value.args
                and isinstance(node.value.args[0], ast.Constant)
                and node.value.args[0].value == "json"):
            out.add(node.targets[0].id)
    return out


def arm_params(source_file: str, arm_start: int, arm_end: int) -> dict[str, str]:
    
    tree = _fn_ast(source_file)
    if tree is None:
        return {}
    bvars = _body_vars(tree)
    
    
    or_param_keys: set[str] = set()
    for node in ast.walk(tree):
        if not (hasattr(node, "lineno")
                and arm_start <= node.lineno <= arm_end
                and isinstance(node, ast.BoolOp)
                and isinstance(node.op, ast.Or)):
            continue
        for side in node.values:
            if (isinstance(side, ast.Call)
                    and isinstance(side.func, ast.Attribute)
                    and side.func.attr == "get"
                    and isinstance(side.func.value, ast.Name)
                    and side.func.value.id in bvars
                    and side.args
                    and isinstance(side.args[0], ast.Constant)):
                or_param_keys.add(side.args[0].value)
    params: dict[str, str] = {}
    for node in ast.walk(tree):
        if not hasattr(node, "lineno"):
            continue                           
        if not (arm_start <= node.lineno <= arm_end):
            continue
        
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in bvars
                and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            if node.args[0].value not in or_param_keys:
                params[node.args[0].value] = "v"
        
        if (isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id in bvars
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)):
            if node.slice.value not in or_param_keys:
                params[node.slice.value] = "v"
    return params


def dispatch_arms(source_file: str) -> list[tuple[str, int, int]]:
    try:
        tree = ast.parse(Path(source_file).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    arms: list[tuple[str, int]] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if not (isinstance(node, (ast.If, ast.IfExp))
                    and isinstance(node.test, ast.Compare)):
                continue
            t = node.test
            if (len(t.ops) == 1 and isinstance(t.ops[0], ast.Eq)
                    and isinstance(t.left, ast.Name) and t.left.id == "op"
                    and isinstance(t.comparators[0], ast.Constant)
                    and isinstance(t.comparators[0].value, str)):
                arms.append((t.comparators[0].value, node.lineno))
    arms.sort(key=lambda a: a[1])
    max_line = 0
    try:
        max_line = len(Path(source_file).read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeDecodeError):
        pass
    out: list[tuple[str, int, int]] = []
    for i, (name, start) in enumerate(arms):
        end = (arms[i + 1][1] - 1) if i + 1 < len(arms) else max_line
        out.append((name, start, end))
    return out


def _row_write_dict_keys(fact: StateFactCandidate) -> list[str]:
    
    try:
        tree = ast.parse(Path(fact.source_file).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and node.lineno == fact.lineno
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Subscript)
                and isinstance(node.value, ast.Dict)):
            return [k.value for k in node.value.keys
                    if isinstance(k, ast.Constant)]
    return []


def _arm_of(fact: StateFactCandidate,
            arms: list[tuple[str, int, int]]) -> str | None:
    for name, start, end in arms:
        if start <= fact.lineno <= end:
            return name
    return None


def _same_file(a: str, b: str) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return a == b

def synthesize_appmodel(ir, facts: list[StateFactCandidate],
                        goal: StateGoal) -> AppModel:
    
    arms = dispatch_arms(goal.file)
    eps: dict[str, Endpoint] = {}

    def _ep(name: str, line: int) -> Endpoint:
        if name not in eps:
            eps[name] = Endpoint(func=f"_handle[{name}]", route=f"op={name}",
                                 methods=["POST"], file=goal.file, line=line)
        return eps[name]

    for f in facts:
        if not _same_file(f.source_file, goal.file):
            continue
        arm = _arm_of(f, arms)
        if arm is None:
            continue
        ep = _ep(arm, arms[0][1])
        if f.operation == StateOperation.WRITE:
            if f.domain.value == "SESSION":
                ep.effects.append(Effect(var=f.object_ref, op="set",
                                         value="True", file=f.source_file,
                                         line=f.lineno))
            else:                                  
                ep.effects.append(Effect(var=f.object_ref, op="set",
                                         value="True", file=f.source_file,
                                         line=f.lineno))
                for key in _row_write_dict_keys(f):   
                    ep.effects.append(Effect(
                        var=f"{f.object_ref}.{key}", op="set", value="*",
                        file=f.source_file, line=f.lineno))
        elif (f.operation == StateOperation.READ
              and f.relevance.value == "CONTROL"):
            if f.structured_predicate is None:
                continue
            opv = f.structured_predicate.operator.value
            if opv == "EXISTS":
                ep.preconditions.append(Precondition(
                    var=f.object_ref, op="truthy",
                    file=f.source_file, line=f.lineno))
            elif opv in ("EQ", "NE", "IN", "NOT_IN"):
                ep.preconditions.append(Precondition(
                    var=f.object_ref, op="eq", value="*",
                    file=f.source_file, line=f.lineno))
    return AppModel(app_root=goal.file, framework="synthetic",
                    endpoints=list(eps.values()))


def _param_feeding_var(source_file: str, arms, arm_name: str,
                       var: str) -> str | None:
    
    key = var.split(".", 1)[1] if "." in var else var
    tree = _fn_ast(source_file)
    if tree is None:
        return None
    s, e = next(((s0, e0) for n, s0, e0 in arms if n == arm_name), (0, 0))
    bvars = _body_vars(tree)
    param_of: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (hasattr(node, "lineno") and s <= node.lineno <= e):
            continue
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            tgt, val = node.targets[0].id, node.value
            if (isinstance(val, ast.Call)
                    and isinstance(val.func, ast.Attribute)
                    and val.func.attr == "get"
                    and isinstance(val.func.value, ast.Name)
                    and val.func.value.id in bvars
                    and val.args and isinstance(val.args[0], ast.Constant)):
                param_of[tgt] = str(val.args[0].value)
        
        if (isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Subscript)
                and isinstance(node.targets[0].value, ast.Name)
                and node.targets[0].value.id == "session"
                and isinstance(node.targets[0].slice, ast.Constant)
                and str(node.targets[0].slice.value) == key
                and isinstance(node.value, ast.Name)
                and node.value.id in param_of):
            return param_of[node.value.id]
    return None


def _insert_identity_refresh(goal, model, segment, arms,
                             source_file: str) -> None:
    ne = [p for p in goal.constraints
          if p.operator.value == "NE" and isinstance(p.value, str)
          and p.value.startswith("session.")]
    if not ne:
        return
    var = ne[0].value
    producer = next((ep for ep in model.endpoints
                     if any(eff.var == var for eff in ep.effects)), None)
    if producer is None:
        return
    arm_name = producer.route.removeprefix("op=")
    s, e = next(((s0, e0) for n, s0, e0 in arms if n == arm_name), (0, 0))
    from stateforge.core.model import PlanStep

    refresh = PlanStep(
        action=f"POST op={arm_name}",
        json={"op": arm_name, **arm_params(source_file, s, e)})
    feed = _param_feeding_var(source_file, arms, arm_name, var)
    if feed:
        used = {st.json.get(feed) for st in segment.steps}
        fresh = "v2" if "v2" not in used else "v3"
        refresh.json[feed] = fresh
    
    insert_at = len(segment.steps) - 1
    for i in range(len(segment.steps) - 1, -1, -1):
        if segment.steps[i].action != f"POST op={arm_name}":
            insert_at = i
            break
    segment.steps.insert(insert_at, refresh)
    segment.notes.append(
        f"identity-refresh: {arm_name}({var} 换新值,NE 约束"
        f" {ne[0].subject}≠{var} 的时序构造)")


def _goal_atom(goal: StateGoal) -> str:
    
    for p in goal.constraints:
        if p.subject.startswith(("db.", "DB")) and p.operator.value != "EXISTS":
            return f"{p.subject}=*"
    for p in reversed(goal.constraints):
        return f"{p.subject}=True"
    return ""


def plan_for_block(ir, facts: list[StateFactCandidate],
                   target_block: str) -> tuple[StateGoal, object] | None:
    
    goal = derive_state_goal(ir, facts, target_block)
    if goal is None or not goal.constraints:
        return None
    blk = ir.blocks.get(target_block)
    if blk is None:
        return None
    arms = dispatch_arms(goal.file)
    model = synthesize_appmodel(ir, facts, goal)
    if not model.endpoints:
        return None
    sstg = build_sstg(model)
    atom = _goal_atom(goal)
    spec = GoalSpec(name=f"cover:{target_block.split('::')[-3]}",
                    vuln_class="state", kind="reach_state",
                    target=atom, max_depth=4)
    segment = plan_backward(model, sstg, spec)

    from stateforge.core.model import PlanStep
    final_arm = _arm_of_row(arms, blk.start_line)
    if final_arm and not any(s.action == f"POST op={final_arm}"
                             for s in segment.steps):
        segment.steps.append(PlanStep(action=f"POST op={final_arm}"))
        segment.notes.append(
            f"final-action: {final_arm}(目标块所在臂,消费状态命中深块)")

    
    
    
    eq_values = {p.subject: p.value for p in goal.constraints
                 if p.operator.value == "EQ" and isinstance(p.value, str)}
    eff_vars_by_route = {ep.route: {e.var for e in ep.effects}
                         for ep in model.endpoints}
    for step in segment.steps:
        arm_name = step.action.removeprefix("POST op=")
        s, e = next(((s0, e0) for n, s0, e0 in arms if n == arm_name),
                    (0, 0))
        params = arm_params(goal.file, s, e)
        for var in eff_vars_by_route.get(f"op={arm_name}", ()):
            key = var.split(".", 1)[1] if "." in var else var
            if key in params and var in eq_values:
                params[key] = eq_values[var]
        step.json = {"op": arm_name, **params}
    _insert_identity_refresh(goal, model, segment, arms, goal.file)
    return goal, segment


def _arm_of_row(arms: list[tuple[str, int, int]], lineno: int) -> str | None:
    for name, start, end in arms:
        if start <= lineno <= end:
            return name
    return None
