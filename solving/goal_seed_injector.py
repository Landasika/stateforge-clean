from __future__ import annotations
from pathlib import Path
from stateforge.solving.state_seed_injector import STATE_BUDGET
def _deep_block_candidates(ir, target: Path,
                           covered: set[str]) -> list[str]:
    
    src_name = target.name
    out = []
    for b in ir.blocks.values():
        if (src_name in b.file and b.function == "_handle"
                and b.kind == "block" and b.id not in covered
                and any("(" in s and not s.startswith("HITS")
                        for s in b.statements)):
            out.append(b.id)
    return sorted(out, key=lambda bid: ir.blocks[bid].start_line)
def inject_goal_seeds(ir, target, state, corpus_dir,
                      budget: int = STATE_BUDGET) -> int:
    
    from stateforge.solving.goal_checkpoint import (GoalCheckpoint,
                                                    inject_checkpoint_seed)
    from stateforge.state.extractor import extract_state_facts
    from stateforge.state.goal_to_plan import plan_for_block

    covered = set(state.get("blocks", []))
    candidates = _deep_block_candidates(ir, Path(target), covered)
    if not candidates:
        return 0
    facts = extract_state_facts(Path(target).parent, ir=ir)
    written = 0
    for bid in candidates:
        if written >= budget:
            break
        planned = plan_for_block(ir, facts, bid)
        if planned is None:
            continue
        goal, segment = planned
        ckpt = GoalCheckpoint(
            checkpoint_id=f"fs-{abs(hash(bid)) % 10**10}",
            target_block=bid, source_file=str(target),
            goal_constraints=[p.to_dict() for p in goal.constraints],
            steps=[{"json": dict(s.json)} for s in segment.steps],
            hits=[],
            step_evidence=[{"action": s.action} for s in segment.steps])
        if inject_checkpoint_seed(ckpt, Path(corpus_dir)):
            written += 1
    return written
