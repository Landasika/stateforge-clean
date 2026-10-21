from __future__ import annotations
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from stateforge.core.model import PlanSegment, PlanStep
from stateforge.fuzzing.corpus_manager import CorpusManager
from stateforge.fuzzing.entry_driver import encode_sequence_seed


@dataclass
class GoalCheckpoint:
    

    checkpoint_id: str
    target_block: str
    source_file: str
    goal_constraints: list[dict]          
    steps: list[dict]                     
    hits: list[str] = field(default_factory=list)
    step_evidence: list[dict] = field(default_factory=list)
    created_at: float = 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=1)

    def save(self, directory: str | Path) -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.checkpoint_id}.json"
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "GoalCheckpoint":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**d)

    def sequence_seed(self) -> bytes:
        
        return encode_sequence_seed(self.steps)

    def to_segment(self) -> PlanSegment:
        steps = []
        for i, s in enumerate(self.steps):
            j = dict(s.get("json", {}))
            arm = j.get("op", f"step:{i}")       
            steps.append(PlanStep(action=f"POST op={arm}", json=j))
        return PlanSegment(goal=f"checkpoint:{self.checkpoint_id}",
                           steps=steps)

def checkpoint_from_execution(target_block: str, source_file: str,
                              goal, execution) -> GoalCheckpoint | None:
    
    if not execution.target_covered or not execution.steps:
        return None
    step_jsons = [dict(s.request) for s in execution.steps]
    payload = json.dumps(
        {"target_block": target_block,
         "steps": step_jsons}, sort_keys=True).encode()
    return GoalCheckpoint(
        checkpoint_id=f"gc-{hashlib.sha256(payload).hexdigest()[:12]}",
        target_block=target_block,
        source_file=str(source_file),
        goal_constraints=[p.to_dict() for p in goal.constraints],
        steps=[{"json": j} for j in step_jsons],
        hits=list(execution.hits),
        step_evidence=[
            {"action": s.action, "ok": s.ok, "write_block": s.write_block,
             "covered": s.n_covered} for s in execution.steps])


def inject_checkpoint_seed(ckpt: GoalCheckpoint,
                           corpus_dir: str | Path) -> str | None:
    
    corpus_dir = Path(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    spool = CorpusManager(corpus_dir.parent / "goal_spool")
    data = ckpt.sequence_seed()
    cid = spool.save(data, epoch=0, new_blocks=0, new_edges=0,
                     discovered_blocks=0, discovered_edges=0,
                     interesting_reason="goal_checkpoint",
                     origin="GOAL")
    if cid:
        (corpus_dir / cid).write_bytes(data)
    return cid

def replay_checkpoint(ckpt: GoalCheckpoint, ir, facts,
                      arms) -> tuple:
    
    from stateforge.runtime.plan_executor import (_load_target_module,
                                                  execute_plan)

    mod = _load_target_module(ckpt.source_file)
    return execute_plan(ckpt.to_segment(), mod, ir, facts,
                        ckpt.target_block, ckpt.source_file, arms)
