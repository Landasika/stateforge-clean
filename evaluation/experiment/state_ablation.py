from __future__ import annotations
import argparse
import itertools
import json
import random
import statistics
from pathlib import Path
from stateforge.core.ir import ProgramIR
from stateforge.fuzzing.corpus_manager import CorpusManager
from stateforge.fuzzing.entry_driver import encode_sequence_seed
from stateforge.solving.state_seed_injector import (NEUTRAL, STATE_BUDGET,
                                                    reached_state_atoms,
                                                    synthesize_micro_model)
from stateforge.solving.vulnshop_state_bridge import (appmodel_path,
                                                      reached_atoms)
ARMS = ("E", "E-rand", "E-always")
RAND_MAX_LEN = 4        
_SAMPLE_TRIES = 64      
def _sstg_of(target) -> tuple[object | None, object | None, object | None]:
    amp = appmodel_path(target)
    if amp is not None:
        return None, amp, amp.sstg
    micro = synthesize_micro_model(target)
    if micro is None:
        return None, None, None
    return micro, None, micro.sstg
def action_set(target) -> list[str]:
    _micro, _amp, sstg = _sstg_of(target)
    if sstg is None:
        return []
    return sorted(n for n, d in sstg.nodes(data=True)
                  if d.get("kind") == "action")
def requires_producers(target) -> tuple[dict[str, list[str]],
                                        dict[str, list[str]]]:
    _micro, _amp, sstg = _sstg_of(target)
    requires: dict[str, list[str]] = {}
    producers: dict[str, list[str]] = {}
    if sstg is not None:
        for u, v, d in sstg.edges(data=True):
            kind = d.get("kind")
            if kind == "requires":
                requires.setdefault(u, []).append(v)
            elif kind == "produces":
                producers.setdefault(v, []).append(u)
    return requires, producers


def is_legal_prefix(seq: list[str], requires: dict[str, list[str]],
                    producers: dict[str, list[str]]) -> bool:
    
    prefix: set[str] = set()
    for action in seq:
        for atom in requires.get(action, ()):
            ps = producers.get(atom)
            if ps and not (set(ps) & prefix):
                return False
        prefix.add(action)
    return True


def sample_legal_sequence(sstg, rng: random.Random,
                          max_len: int = RAND_MAX_LEN) -> list[str] | None:
    actions = sorted(n for n, d in sstg.nodes(data=True)
                     if d.get("kind") == "action")
    if not actions:
        return None
    requires: dict[str, list[str]] = {}
    producers: dict[str, list[str]] = {}
    for u, v, d in sstg.edges(data=True):
        kind = d.get("kind")
        if kind == "requires":
            requires.setdefault(u, []).append(v)
        elif kind == "produces":
            producers.setdefault(v, []).append(u)
    for _ in range(_SAMPLE_TRIES):
        seq = [actions[rng.randrange(len(actions))]
               for _ in range(rng.randint(1, max_len))]
        if is_legal_prefix(seq, requires, producers):
            return seq
    return None




def _render_random_step(action: str, micro=None, model=None) -> dict:
    
    if micro is not None:
        op = action.partition(" ")[2]
        entry = micro.ops.get(op)
        params = entry.params if entry is not None else []
        return {"json": {"op": op, **{p: NEUTRAL for p in params}}}
    method, _, route = action.partition(" ")
    path = route
    json_body: dict[str, str] = {}
    for ep in getattr(model, "endpoints", ()) or ():
        if (ep.methods[0] if ep.methods else "GET") != method \
                or ep.route != route:
            continue
        for p in ep.params:
            if p.location == "path":
                path = path.replace(f"<int:{p.name}>", f"?{p.name}") \
                           .replace(f"<{p.name}>", f"?{p.name}")
            elif p.location == "json":
                json_body.setdefault(p.name, NEUTRAL)
        break
    req = {"method": method or "GET", "path": path}
    if json_body:
        req["json"] = json_body
    return req





def _audit(audit_path: Path, record: dict) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

def inject_random_seeds(ir, target, state, corpus_dir,
                        budget: int = STATE_BUDGET, seed=0,
                        max_len: int = RAND_MAX_LEN) -> int:
    
    if budget <= 0:
        return 0
    target = Path(target)
    micro, amp, sstg = _sstg_of(target)
    if sstg is None:
        return 0
    if amp is not None:                        
        reached = reached_atoms(ir, state, amp)
        if not (set(amp.atoms) - reached):
            return 0
        model = amp.model
    else:
        reached = reached_state_atoms(ir, target, state)
        if not {g.atom for g in micro.guards if g.atom} - reached:
            return 0
        model = None

    rng = random.Random(str(seed))
    corpus_dir = Path(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    spool = CorpusManager(corpus_dir.parent / "state_spool")
    audit_path = corpus_dir.parent / "epochs" / "state_injections.jsonl"
    written = 0
    for _ in range(budget):
        seq = sample_legal_sequence(sstg, rng, max_len)
        if seq is None:
            _audit(audit_path, {"path": "random", "status": "NO_LEGAL",
                                "seed": str(seed)})
            break
        steps = [_render_random_step(a, micro=micro, model=model)
                 for a in seq]
        data = encode_sequence_seed(steps)
        cid = spool.save(data, epoch=0, new_blocks=0, new_edges=0,
                         discovered_blocks=0, discovered_edges=0,
                         interesting_reason="state_rand", origin="STATE")
        record = {"path": "random", "seed": str(seed), "length": len(seq),
                  "steps": [s.get("json", {}).get("op")
                            or f"{s.get('method')} {s.get('path')}"
                            for s in steps]}
        if cid:
            (corpus_dir / cid).write_bytes(data)
            written += 1
            record.update(status="INJECTED", seed_id=cid)
        else:
            record.update(status="DUPLICATE")
        _audit(audit_path, record)
    return written


def _rand_injector_factory(run_seed: int, max_len: int = RAND_MAX_LEN):
    
    boundary = itertools.count()

    def _inject(ir, target, state, corpus_dir, budget=STATE_BUDGET):
        return inject_random_seeds(ir, target, state, corpus_dir,
                                   budget=budget,
                                   seed=f"{run_seed}:b{next(boundary)}",
                                   max_len=max_len)

    return _inject

def run_ablation(target: str, ir: str, out: Path, runs: int = 2,
                 epochs: int = 3, seconds: float = 3.0, seed0: int = 7,
                 mode: str = "frontier", use_feedback: bool = True,
                 max_len: int = RAND_MAX_LEN) -> dict:
    
    from stateforge.evaluation.experiment.epoch import run_epochs
    from stateforge.evaluation.experiment.state_arm_report import (
        _merge_state, state_metrics)          
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    
    
    tgt = Path(target)
    atoms_measurable = (synthesize_micro_model(tgt) is not None
                        if tgt.is_file() else None)
    report: dict = {"target": str(target), "ir": str(ir), "runs": runs,
                    "epochs": epochs, "seconds": seconds, "seed0": seed0,
                    "mode": mode, "arms": {a: {"per_run": {}} for a in ARMS},
                    "pairwise": {},
                    "state_atoms_measurable": atoms_measurable}
    if atoms_measurable is False:
        report["state_atoms_note"] = (
            "状态原子三指标仅微靶路径可测;本靶无微模型"
            "(synthesize_micro_model=None,AppModel 路径),"
            "atoms/transitions/deep_blocks 为未测,非测得零")

    
    
    
    
    
    from stateforge.evaluation.experiment.campaign import _manifest

    class _MArgs:                                    
        pass
    margs = _MArgs()
    margs.runs, margs.epochs = runs, epochs
    margs.seconds, margs.seed0 = seconds, seed0
    report["manifest"] = _manifest(target, ir, out, margs)

    for k in range(runs):
        seed = seed0 + k * 100
        run = f"run{k:02d}"
        for arm in ARMS:
            kwargs: dict = {}
            if arm == "E-rand":
                kwargs["state_injector"] = _rand_injector_factory(seed,
                                                                 max_len)
            elif arm == "E-always":
                kwargs["state_trigger"] = "always"
            res = run_epochs(str(target), str(ir), out / run / arm, seconds,
                             epochs, seed, arm, mode=mode,
                             use_feedback=use_feedback, policy="state",
                             **kwargs)
            report["arms"][arm]["per_run"][run] = {
                "seed": seed,
                "blocks": res["final_blocks"],
                "edges": res["final_edges"],
                "executions": res["total_executions"],
                "injections_total": res.get("state_injections_total", 0)}

    for arm in ARMS:                           
        arm_rep = report["arms"][arm]
        state_runs = []
        for k in range(runs):
            run = f"run{k:02d}"
            st = state_metrics(ir, target, out / run / arm, ledger=True)
            state_runs.append({"run": run, **st})
            arm_rep["per_run"][run].update(
                atoms_reached=st["atoms_reached"],
                transitions_observed=st["transitions_observed"],
                deep_state_blocks=st["deep_state_blocks"])
        arm_rep["state_runs"] = state_runs
        arm_rep["state"] = _merge_state(state_runs)
        blocks = [arm_rep["per_run"][f"run{k:02d}"]["blocks"]
                  for k in range(runs)]
        vals = [b for b in blocks if b is not None]
        arm_rep["mean_blocks"] = round(statistics.mean(vals), 1) if vals \
            else None
        edges = [arm_rep["per_run"][f"run{k:02d}"]["edges"]
                 for k in range(runs)]
        vals = [e for e in edges if e is not None]
        arm_rep["mean_edges"] = round(statistics.mean(vals), 1) if vals \
            else None

    for key, other, label in (                
            ("E_minus_E-rand", "E-rand", "planner_contribution"),
            ("E_minus_E-always", "E-always", "trigger_value")):
        e_per = report["arms"]["E"]["per_run"]
        o_per = report["arms"][other]["per_run"]
        blocks_d = [e_per[f"run{k:02d}"]["blocks"] - o_per[f"run{k:02d}"]["blocks"]
                    for k in range(runs)
                    if e_per[f"run{k:02d}"]["blocks"] is not None
                    and o_per[f"run{k:02d}"]["blocks"] is not None]
        atoms_d = [e_per[f"run{k:02d}"]["atoms_reached"]
                   - o_per[f"run{k:02d}"]["atoms_reached"]
                   for k in range(runs)]
        report["pairwise"][key] = {
            "label": label,
            "blocks": round(statistics.mean(blocks_d), 1) if blocks_d else None,
            "atoms": round(statistics.mean(atoms_d), 1) if atoms_d else None,
            "blocks_per_run": {f"run{k:02d}":
                               e_per[f"run{k:02d}"]["blocks"]
                               - o_per[f"run{k:02d}"]["blocks"]
                               for k in range(runs)
                               if e_per[f"run{k:02d}"]["blocks"] is not None
                               and o_per[f"run{k:02d}"]["blocks"] is not None}}
    return report


def render_text(report: dict) -> str:
    unmeasured = report.get("state_atoms_measurable") is False
    lines: list[str] = [
        f"state ablation — {report['target']} "
        f"(runs={report['runs']} epochs={report['epochs']} "
        f"seconds={report['seconds']})"]
    lines.append("arm       mean_blocks  mean_edges  atoms  transitions  "
                 "deep_blocks  injections")
    for arm in ARMS:
        a = report["arms"][arm]
        st = a.get("state", {})
        inj = sum(a["per_run"][f"run{k:02d}"]["injections_total"]
                  for k in range(report["runs"]))
        
        atoms = "-" if unmeasured else st.get("atoms_reached", 0)
        trans = "-" if unmeasured else st.get("transitions_observed", 0)
        deep = "-" if unmeasured else st.get("deep_state_blocks", 0)
        lines.append(
            f"{arm:<9} {a['mean_blocks']!s:<11} {a['mean_edges']!s:<10} "
            f"{atoms!s:<6} "
            f"{trans!s:<12} "
            f"{deep!s:<12} {inj}")
    if unmeasured:
        lines.append(f"注: {report.get('state_atoms_note')}")
    pw = report["pairwise"]
    for key, desc in (("E_minus_E-rand", "planner contribution"),
                      ("E_minus_E-always", "R2 trigger value")):
        if key in pw:
            atoms_txt = ("n/a(未测:无微模型)" if unmeasured
                         else f"{pw[key]['atoms']:+.1f}")
            lines.append(f"{key}: blocks={pw[key]['blocks']:+.1f} "
                         f"atoms={atoms_txt}  ({desc})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="P4-T4 消融臂:E / E-rand(随机序列)/ E-always(恒注入)")
    parser.add_argument("target")
    parser.add_argument("ir")
    parser.add_argument("--out", default="results/experiment/state_ablation")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--seed0", type=int, default=7)
    parser.add_argument("--max-len", dest="max_len", type=int,
                        default=RAND_MAX_LEN,
                        help="E-rand 随机序列长度上界(U{1..max_len})")
    args = parser.parse_args(argv)
    
    
    
    try:
        ir_blocks = ProgramIR.from_json(args.ir).blocks
    except Exception as exc:                    
        parser.error(f"IR 无法载入: {args.ir}"
                     f"({type(exc).__name__}: {exc});请对靶套件目录重新"
                     " analyze——`python -m stateforge.cli analyze <suite-dir> "
                     "--out results/structural`,再以其 program_ir.json "
                     "作为 ir 参数")
    if not ir_blocks:
        parser.error(
            f"IR 无块(blocks=0): {args.ir};请对靶套件目录重新 analyze——"
            "`python -m stateforge.cli analyze <suite-dir> "
            "--out results/structural`,再以其 program_ir.json 作为 ir 参数")
    report = run_ablation(args.target, args.ir, Path(args.out), runs=args.runs,
                          epochs=args.epochs, seconds=args.seconds,
                          seed0=args.seed0, max_len=args.max_len)
    text = render_text(report)
    print(text)
    out_json = Path(args.out) / "state_ablation.json"
    out_json.write_text(json.dumps(report, indent=1, ensure_ascii=False),
                        encoding="utf-8")
    (Path(args.out) / "state_ablation.txt").write_text(text + "\n",
                                                       encoding="utf-8")
    print(f"\n[out] {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
