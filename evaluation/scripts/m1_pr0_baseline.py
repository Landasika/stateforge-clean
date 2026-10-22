import hashlib
import json
import platform
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stateforge.analysis.static.icfg import build_icfg
from stateforge.adapters.callable import CallableAdapter
from examples.m1_target import target
from stateforge.fuzzing.feedback.corpus import GuidedCorpus
from stateforge.fuzzing.guidance.campaign import CampaignConfig, GuidedCampaign
from stateforge.fuzzing.guidance.mutator import BasicMutator
from stateforge.fuzzing.guidance.target import BasicBlockTarget

EXAMPLES = ROOT / "examples"
SEEDS = [path.read_bytes() for path in sorted((EXAMPLES / "seeds").iterdir())]
IR = build_icfg(EXAMPLES)
TARGET_ID = IR.functions["m1_target.target_block"].entry
TRIALS = 20
GROUPS = {
    "A": {"selection_policy": "uniform", "energy_policy": "fixed",
          "fixed_energy": 1},
    "B": {"selection_policy": "distance", "energy_policy": "fixed",
          "fixed_energy": 1},
    "C": {"selection_policy": "distance", "energy_policy": "distance",
          "fixed_energy": 1},
}


def main() -> int:
    rows = {}
    for group, policy in GROUPS.items():
        group_rows = []
        for trial in range(TRIALS):
            config = CampaignConfig(
                max_executions=20000,
                max_input_size=4096,
                max_corpus_size=1000,
                epsilon=0.20,
                random_seed=trial,
                stop_on_target=True,
                fault_policy="continue",
                min_energy=1,
                max_energy=32,
                selection_policy=policy["selection_policy"],
                energy_policy=policy["energy_policy"],
                fixed_energy=policy["fixed_energy"],
                progress_every=100,
            )
            campaign = GuidedCampaign(
                ir=IR,
                target=BasicBlockTarget(TARGET_ID),
                adapter=CallableAdapter(target),
                corpus=GuidedCorpus(1000),
                mutator=BasicMutator(trial),
                config=config,
            )
            result = campaign.run(SEEDS)
            row = result.to_dict()
            row.update({
                "group": group,
                "trial": trial,
                "config": config.to_dict(),
                "corpus_size": len(campaign.corpus),
                "total_trace_events": campaign.total_trace_events,
            })
            group_rows.append(row)
        reached = [row for row in group_rows if row["target_reached"]]
        executions = [row["executions_to_target"] for row in reached]
        times = [row["wall_clock_time_to_target_seconds"] for row in reached]
        elapsed = [row["elapsed_seconds"] for row in group_rows]
        rows[group] = {
            "policy": policy,
            "runs": group_rows,
            "aggregate": {
                "trials": TRIALS,
                "successes": len(reached),
                "failures": TRIALS - len(reached),
                "success_rate": len(reached) / TRIALS,
                "median_executions_to_target": (
                    statistics.median(executions) if executions else None),
                "mean_executions_to_target": (
                    statistics.mean(executions) if executions else None),
                "min_executions_to_target": (
                    min(executions) if executions else None),
                "max_executions_to_target": (
                    max(executions) if executions else None),
                "median_wall_clock_to_target_seconds": (
                    statistics.median(times) if times else None),
                "mean_wall_clock_to_target_seconds": (
                    statistics.mean(times) if times else None),
                "median_elapsed_seconds": statistics.median(elapsed),
                "mean_executions_per_second": statistics.mean(
                    row["executions"] / row["elapsed_seconds"]
                    for row in group_rows if row["elapsed_seconds"] > 0),
            },
        }
    code_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    payload = {
        "plan": "M2 PR-0 baseline",
        "code_commit": code_commit,
        "branch": branch,
        "generated_at": datetime.now().astimezone().isoformat(),
        "target_basic_block": TARGET_ID,
        "target_source_hash": IR.metadata.get("source_hash"),
        "initial_corpus_sha256": [
            hashlib.sha256(seed).hexdigest() for seed in SEEDS],
        "initial_corpus_hex": [seed.hex() for seed in SEEDS],
        "random_seeds": list(range(TRIALS)),
        "max_executions": 20000,
        "environment": {
            "python": sys.version,
            "python_executable": sys.executable,
            "platform": platform.platform(),
        },
        "groups": rows,
    }
    out = ROOT / "evaluation" / "baselines" / "m1_pr0.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({
        "code_commit": code_commit,
        "branch": branch,
        "target": TARGET_ID,
        "output": str(out),
        "groups": {group: data["aggregate"]
                   for group, data in rows.items()},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
