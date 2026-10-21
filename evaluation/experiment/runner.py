from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path

from stateforge.evaluation.experiment.epoch import run_epochs

GROUPS = ("A_native", "A_measure", "B", "C", "D1", "D2R", "D2P", "E", "F")


def run_experiment(target: str, ir: str, out: Path, epochs: int,
                   seconds_per_epoch: float, seed: int,
                   groups: tuple[str, ...] | None = None) -> dict:
    
    if groups is None:
        groups = GROUPS
    else:
        groups = tuple(groups)
        unknown = [g for g in groups if g not in GROUPS]
        if unknown or not groups:
            raise ValueError(f"未知组 {unknown or '空子集'};"
                             f" 有效组: {', '.join(GROUPS)}")
    out.mkdir(parents=True, exist_ok=True)
    total = epochs * seconds_per_epoch
    t0 = __import__("time").monotonic()
    report = {"target": target, "ir": str(ir), "seed": seed, "epochs": epochs,
              "seconds_per_epoch": seconds_per_epoch, "groups": {}}
    
    if "A_native" in groups:
        report["groups"]["A_native"] = run_epochs(
            target, ir, out / "A_native", total, 1, seed, "A_native",
            mode="off", use_feedback=False, t0=t0)
    if "A_measure" in groups:
        report["groups"]["A_measure"] = run_epochs(
            target, ir, out / "A_measure", total, 1, seed, "A_measure",
            mode="measure", use_feedback=False, t0=t0)
    if "B" in groups:
        report["groups"]["B"] = run_epochs(
            target, ir, out / "B", seconds_per_epoch, epochs, seed, "B",
            mode="measure", use_feedback=False, t0=t0)
    if "C" in groups:
        report["groups"]["C"] = run_epochs(
            target, ir, out / "C", seconds_per_epoch, epochs, seed, "C",
            mode="feedback", use_feedback=True, t0=t0)
    
    if "D1" in groups:
        report["groups"]["D1"] = run_epochs(
            target, ir, out / "D1", seconds_per_epoch, epochs, seed, "D1",
            mode="frontier", use_feedback=True, t0=t0)
    
    if "D2R" in groups:
        report["groups"]["D2R"] = run_epochs(
            target, ir, out / "D2R", seconds_per_epoch, epochs, seed, "D2R",
            mode="frontier", use_feedback=True, t0=t0, policy="reinjection")
    
    
    
    if "D2P" in groups:
        report["groups"]["D2P"] = run_epochs(
            target, ir, out / "D2P", seconds_per_epoch, epochs, seed, "D2P",
            mode="frontier", use_feedback=True, t0=t0, policy="portfolio")
    
    
    if "E" in groups:
        report["groups"]["E"] = run_epochs(
            target, ir, out / "E", seconds_per_epoch, epochs, seed, "E",
            mode="frontier", use_feedback=True, t0=t0, policy="state")
    
    if "F" in groups:
        from stateforge.solving.goal_seed_injector import inject_goal_seeds
        report["groups"]["F"] = run_epochs(
            target, ir, out / "F", seconds_per_epoch, epochs, seed, "F",
            mode="frontier", use_feedback=True, t0=t0, policy="state",
            state_injector=inject_goal_seeds)
    (out / "experiment.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase-2 八组配对实验")
    parser.add_argument("target")
    parser.add_argument("ir")
    parser.add_argument("--out", required=True)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    report = run_experiment(args.target, args.ir, Path(args.out),
                            args.epochs, args.seconds, args.seed)
    for name, g in report["groups"].items():
        print(f"[{name}] exec={g['total_executions']} wall={g['wall_total']}s "
              f"blocks={g['final_blocks']} edges={g['final_edges']}"
              + (f" nsg={g['novel_seed_gain']['novel_seed_gain']}"
                 if "novel_seed_gain" in g else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
