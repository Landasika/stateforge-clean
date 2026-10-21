from __future__ import annotations
import json
import statistics
import subprocess
import sys
from pathlib import Path
from stateforge.evaluation.experiment.epoch import run_epochs
def run_target(target_py: str, ir_path: str, name: str, out: Path,
               runs: int, epochs: int, seconds: int) -> dict:
    results = []
    for k in range(runs):
        seed = 7 + k * 100
        rd = out / f"run{k:02d}"
        print(f"  [{name}] run {k+1}/{runs}", flush=True)

        total_time = epochs * seconds

        
        a = run_epochs(target_py, ir_path, rd / "A", total_time, 1, seed,
                        "A", mode="off", use_feedback=False)
        
        b = run_epochs(target_py, ir_path, rd / "B", seconds, epochs, seed,
                        "B", mode="feedback", use_feedback=True)
        
        c = run_epochs(target_py, ir_path, rd / "C", seconds, epochs, seed,
                        "C", mode="frontier", use_feedback=True,
                        policy="portfolio")
        
        d = run_epochs(target_py, ir_path, rd / "D", seconds, epochs, seed,
                        "D", mode="frontier", use_feedback=True,
                        policy="llm")
        
        e = run_epochs(target_py, ir_path, rd / "E", seconds, epochs, seed,
                        "E", mode="frontier", use_feedback=True,
                        policy="state")
        
        
        from stateforge.solving.goal_seed_injector import inject_goal_seeds
        f = run_epochs(target_py, ir_path, rd / "F", seconds, epochs, seed,
                       "F", mode="frontier", use_feedback=True,
                       policy="state", state_injector=inject_goal_seeds)
        results.append({
            "seed": seed,
            "A_tput": round(a["total_executions"] /
                            max(a["wall_span"], 1), 0),
            "B_blocks": b["final_blocks"], "B_edges": b["final_edges"],
            "C_blocks": c["final_blocks"], "C_edges": c["final_edges"],
            "D_blocks": d["final_blocks"], "D_edges": d["final_edges"],
            "E_blocks": e["final_blocks"], "E_edges": e["final_edges"],
            "F_blocks": f["final_blocks"], "F_edges": f["final_edges"],
        })

    s = {"target": name, "runs": runs,
         "total_time": epochs * seconds,
         "per_run": [{k: v for k, v in r.items()} for r in results]}
    for arm in ("B", "C", "D", "E", "F"):
        vals = [r[f"{arm}_blocks"] for r in results]
        s[f"{arm}_mean"] = round(statistics.mean(vals), 1)
        s[f"{arm}_stdev"] = round(statistics.stdev(vals), 2) \
            if len(vals) > 1 else 0
    s["D_minus_C"] = round(statistics.mean(
        [r["D_blocks"] - r["C_blocks"] for r in results]), 1)
    s["D_minus_B"] = round(statistics.mean(
        [r["D_blocks"] - r["B_blocks"] for r in results]), 1)
    s["E_minus_D"] = round(statistics.mean(
        [r["E_blocks"] - r["D_blocks"] for r in results]), 1)
    s["F_minus_E"] = round(statistics.mean(
        [r["F_blocks"] - r["E_blocks"] for r in results]), 1)
    return s


MICROPLUS_TARGETS = [
    ("stateforge/targets/microplus/s2_api_path.py", "S2_api_path"),
    ("stateforge/targets/microplus/s1_role_chain.py", "S1_role_chain"),
    ("stateforge/targets/microplus/hash_gates.py", "hash_gates"),
]
STATEFUL_TARGETS = [
    ("stateforge/targets/stateful/t_state_chain.py", "t_state_chain"),
    ("stateforge/targets/stateful/t_state_gate.py", "t_state_gate"),
]
SUITES = {"microplus": MICROPLUS_TARGETS, "stateful": STATEFUL_TARGETS}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="results/experiment/phase42g_v3")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=8)
    parser.add_argument("--suite", choices=sorted(SUITES), default="microplus",
                        help="microplus=旧三靶(默认);stateful=状态门靶")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    all_s = {}

    
    suite_dir = str(Path(MICROPLUS_TARGETS[0][0]).parent
                    if args.suite == "microplus"
                    else Path(STATEFUL_TARGETS[0][0]).parent)
    ir_dir = out / "ir"
    subprocess.run([sys.executable, "-m", "stateforge.cli", "analyze",
                    suite_dir, "--out", str(ir_dir)],
                   capture_output=True, check=True)
    ir_path = str(ir_dir / "program_ir.json")
    
    (out / "run_manifest.json").write_text(json.dumps(
        {"suite": args.suite, "runs": args.runs, "epochs": args.epochs,
         "seconds": args.seconds, "ir": ir_path,
         "targets": {name: tp for tp, name in SUITES[args.suite]}},
        ensure_ascii=False, indent=1), encoding="utf-8")
    for tp, name in SUITES[args.suite]:
        s = run_target(tp, ir_path, name, out / name,
                        args.runs, args.epochs, int(args.seconds))
        all_s[name] = s
        print(f"  → {name}: B={s['B_mean']} C={s['C_mean']} "
              f"D={s['D_mean']} E={s['E_mean']} F={s['F_mean']} "
              f"(D-C={s['D_minus_C']:+.1f} "
              f"D-B={s['D_minus_B']:+.1f} E-D={s['E_minus_D']:+.1f} "
              f"F-E={s['F_minus_E']:+.1f})",
              flush=True)

    (out / "all_summaries.json").write_text(
        json.dumps(all_s, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n[out] {out / 'all_summaries.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
