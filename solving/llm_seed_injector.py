from __future__ import annotations
import json
import time
from pathlib import Path

from stateforge.core.ir import ProgramIR
from stateforge.solving.guard_recovery import (_TestIndex,
                                                    recover_guard)
from stateforge.solving.enhanced_provenance import resolve_enhanced
from stateforge.solving.llm_solver import LLMSemanticSolver
from stateforge.solving.proposal import ProposalStatus
from stateforge.solving.proposal_validator import validate
from stateforge.fuzzing.constraint_mutator import (MutationError,
                                                apply_hint)
from stateforge.fuzzing.corpus_manager import CorpusManager
from stateforge.fuzzing.mutation_hint import MutationHint


def inject_llm_seeds(ir: ProgramIR, app_path: Path,
                     coverage_state: dict,
                     corpus_dir: Path, provider,
                     max_seeds: int = 3,
                     min_hits: int = 50) -> list[dict]:
    
    from stateforge.solving.semantic_slice import build_slice
    from stateforge.solving.stalled import StalledFrontier

    covered_blocks = set(coverage_state.get("covered_blocks", []))
    covered_edges = {tuple(e) for e in
                     coverage_state.get("covered_edges", [])}
    if not covered_blocks:
        return []

    index = _TestIndex(ir)
    solver = LLMSemanticSolver(provider)
    records = []

    
    stalled = []
    for e in ir.edges:
        if e.kind not in ("true", "false"):
            continue
        u, v = e.src, e.dst
        if u not in covered_blocks or (u, v) in covered_edges:
            continue
        guard = recover_guard(ir, u, v, e.kind, index)
        if guard.status == "BRANCH_NOT_FOUND":
            continue          
        stalled.append(StalledFrontier((u, v), min_hits, guard))
        if len(stalled) >= max_seeds:
            break

    if not stalled:
        return []

    base_seed = _load_base_seed(corpus_dir)

    for sf in stalled:
        block = ir.blocks[sf.edge[0]]
        prov = resolve_enhanced(ir, app_path, block.function,
                                 sf.guard.lineno)
        slice_ = build_slice(ir, sf, [], prov, app_path)
        try:
            proposal, latency, tokens = solver.solve(slice_)
        except Exception:                          
            records.append({"frontier": sf.frontier_id,
                            "status": "PROVIDER_ERROR"})
            continue

        if proposal.status != ProposalStatus.PROPOSED:
            records.append({"frontier": sf.frontier_id,
                            "status": proposal.status.value})
            continue

        vres = validate(proposal, slice_)
        if not vres.valid:
            records.append({"frontier": sf.frontier_id,
                            "status": f"REJECTED_{vres.rejection_reason}"})
            continue

        
        
        hint = MutationHint(
            frontier_id=sf.frontier_id, guard_id=sf.guard.guard_id,
            source_kind=proposal.source_kind,
            source_key=proposal.source_key,
            current_value=proposal.proposed_value,
            target_value=proposal.proposed_value,
            operator=sf.guard.op,
            desired_polarity=sf.guard.polarity,
            reason="solved", confidence=proposal.confidence)
        try:
            seed = apply_hint(base_seed, hint)
            seed_bytes = json.dumps(seed, sort_keys=True).encode()
            cid = CorpusManager(corpus_dir.parent / "llm_spool").save(
                seed_bytes, epoch=0, new_blocks=0, new_edges=0,
                discovered_blocks=0, discovered_edges=0,
                nearest_frontier=sf.frontier_id,
                interesting_reason="llm_proposal", origin="LLM")
            if cid:
                (corpus_dir / cid).write_bytes(seed_bytes)
                base_seed = seed           
                records.append({"frontier": sf.frontier_id,
                                "status": "INJECTED",
                                "seed_id": cid,
                                "value": str(proposal.proposed_value)[:50]})
            else:
                records.append({"frontier": sf.frontier_id,
                                "status": "DUPLICATE"})
        except MutationError as exc:
            records.append({"frontier": sf.frontier_id,
                            "status": f"MUTATION_ERROR_{exc}"})

    return records


def _load_base_seed(corpus_dir: Path) -> dict:
    
    if corpus_dir.exists():
        for f in sorted(corpus_dir.glob("*")):
            if f.is_file():
                try:
                    data = json.loads(f.read_bytes())
                    if isinstance(data, dict):
                        return data
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
    return {"query": {}, "form": {}, "json": {}, "header": {}, "cookie": {}}
