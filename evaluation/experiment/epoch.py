from __future__ import annotations
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from stateforge.fuzzing.corpus_manager import CorpusManager

EXECUTION_EDGE_KINDS = {"flow", "true", "false", "call", "return"}


def _dir_stats(d: Path) -> dict:
    files = [f for f in d.iterdir() if f.is_file()] if d.exists() else []
    return {"files": len(files), "bytes": sum(f.stat().st_size for f in files)}


def _run_driver(target: str, ir: str, corpus_dir: Path, out_dir: Path,
                seconds: float, mode: str, seed: int, group: str,
                epoch: int) -> None:
    cmd = [sys.executable, "-m", "stateforge.fuzzing.entry_driver",
           target, ir, str(corpus_dir), str(out_dir),
           "--seconds", str(seconds), "--mode", mode,
           "--seed", str(seed), "--epoch", str(epoch), "--group", group]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=seconds * 4 + 120)
    if proc.returncode not in (0, -2, 245):
        raise RuntimeError(f"driver 失败 rc={proc.returncode}: "
                           f"{proc.stderr[-2000:]}")


def _load_epoch_summary(out_dir: Path, group: str, epoch: int) -> dict:
    p = out_dir / f"{group}-e{epoch}-snapshots.jsonl"
    snaps = [json.loads(line) for line in
             p.read_text(encoding="utf-8").splitlines() if line.strip()]
    cand_p = out_dir / f"{group}-e{epoch}-candidates.jsonl"
    cands = [json.loads(line) for line in
             cand_p.read_text(encoding="utf-8").splitlines() if line.strip()] \
        if cand_p.exists() else []
    last = snaps[-1] if snaps else {}
    return {"epoch": epoch, "snapshots": snaps,
            "executions": last.get("executions", 0),
            "blocks": last.get("blocks", 0), "edges": last.get("edges", 0),
            "exec_seconds": last.get("exec_seconds", 0.0),
            "feedback_seconds": last.get("feedback_seconds", 0.0),
            "candidates_saved": len(cands)}


def _novel_seed_gain(workdir: Path) -> dict:
    
    spool = workdir / "epochs" / "spool" / "seeds"
    lf = workdir / "lf_corpus"
    sf_ids = {f.name for f in spool.iterdir()} if spool.exists() else set()
    lf_ids = {CorpusManager.content_id(f.read_bytes())
              for f in lf.iterdir() if f.is_file()} if lf.exists() else set()
    total, overlap = len(sf_ids), len(sf_ids & lf_ids)
    return {"sf_candidates_total": total,
            "sf_already_in_native": overlap,
            "sf_unique_vs_native": total - overlap,
            "novel_seed_gain": round((total - overlap) / total, 4) if total else None}


def _inject_llm_between_epochs(ir, workdir: Path, corpus_dir: Path,
                               target: str,
                               stall_tracker=None, epoch_num: int = 0,
                               prev_blocks: int = 0, prev_edges: int = 0) -> list[dict]:
    
    import json as _json
    from stateforge.solving.llm_seed_injector import inject_llm_seeds

    state_path = workdir / "epochs" / "global_state.json"
    if not state_path.exists():
        return []
    state = _json.loads(state_path.read_text(encoding="utf-8"))
    active_frontiers = {tuple(e) for e in state.get("edge_frontiers", [])
                        if len(e) == 2}
    cur_blocks = len(state.get("covered_blocks", []))
    cur_edges = len(state.get("covered_edges", []))
    new_blocks = cur_blocks - prev_blocks
    new_edges = cur_edges - prev_edges

    if stall_tracker is not None:
        to_inject = stall_tracker.observe_epoch(
            epoch_num, active_frontiers, new_blocks, new_edges)
        if not to_inject:
            return []                        
    provider_path = Path(target).parent / (Path(target).stem + ".llm.py")
    if not provider_path.exists():
        return []                            
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("llm_provider", provider_path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    provider = mod.provider

    from stateforge.core.ir import ProgramIR
    ir_obj = ProgramIR.from_json(ir)
    records = inject_llm_seeds(ir_obj, Path(target), state,
                               corpus_dir, provider)
    if records and stall_tracker is not None:
        for r in records:
            edge = tuple(r.get("frontier", "->").split("->"))
            stall_tracker.mark_injected(edge)
    if records:
        llm_log = workdir / "epochs" / "llm_injections.jsonl"
        with llm_log.open("a", encoding="utf-8") as fh:
            for r in records:
                fh.write(_json.dumps(r, ensure_ascii=False) + "\n")
    return records


def _verified_state_atoms(state: dict) -> set[str]:
    
    ev = state.get("state_evidence") or {}
    return set(ev.get("verified_atoms", []))


def _inject_state_seeds_between_epochs(ir, workdir: Path, corpus_dir: Path,
                                        target: str,
                                        epoch_num: int = 0,
                                        trigger: str = "r2",
                                        injector=None) -> int:
    
    import json as _json
    from stateforge.core.ir import ProgramIR
    from stateforge.solving.state_seed_injector import (STATE_BUDGET,
                                                        inject_state_seeds,
                                                        reached_state_atoms)
    state_path = workdir / "epochs" / "global_state.json"
    if not state_path.exists():
        return 0                                
    state = _json.loads(state_path.read_text(encoding="utf-8"))
    ir_obj = ProgramIR.from_json(ir)

    verified = _verified_state_atoms(state)      
    ledger_path = workdir / "epochs" / "state_ledger.json"
    prior: set = set()
    if ledger_path.exists():
        prior = set(_json.loads(
            ledger_path.read_text(encoding="utf-8")).get("atoms", []))
    now = reached_state_atoms(ir_obj, Path(target), state)
    ledger_path.write_text(
        _json.dumps({"epoch": epoch_num, "atoms": sorted(now),
                     "proxy_reached_atoms": sorted(now),
                     "verified_reached_atoms": sorted(verified)}),
        encoding="utf-8")
    new_atoms = sorted(now - prior)
    if new_atoms:
        if trigger == "always":                 
            _state_audit(workdir, {"epoch": epoch_num,
                                   "status": "INJECT_ALWAYS",
                                   "new_atoms": new_atoms})
        else:                                   
            _state_audit(workdir, {"epoch": epoch_num,
                                   "status": "SKIP_R2_PROGRESS",
                                   "new_atoms": new_atoms})
            return 0
    inj = inject_state_seeds if injector is None else injector
    return inj(ir_obj, Path(target), state, corpus_dir, budget=STATE_BUDGET)
def _state_audit(workdir: Path, record: dict) -> None:
    path = workdir / "epochs" / "state_injections.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _llm_audit(workdir: Path, record: dict) -> None:
    
    try:
        path = workdir / "epochs" / "llm_injections.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass

def _state_boundary(workdir: Path, epoch: int, injected: int) -> dict:
    
    out: dict = {"epoch": epoch, "atoms_reached": None, "injected": injected}
    ledger = workdir / "epochs" / "state_ledger.json"
    if ledger.exists():
        data = json.loads(ledger.read_text(encoding="utf-8"))
        out["atoms_reached"] = len(data.get("atoms", []))
        if "proxy_reached_atoms" in data:
            out["proxy_atoms_reached"] = len(data["proxy_reached_atoms"])
        if "verified_reached_atoms" in data:
            out["verified_atoms_reached"] = len(data["verified_reached_atoms"])
    audit = workdir / "epochs" / "state_injections.jsonl"
    if audit.exists():
        lines = audit.read_text(encoding="utf-8").splitlines()
        if lines:
            last = json.loads(lines[-1])
            if last.get("epoch") == epoch \
                    and last.get("status") == "SKIP_R2_PROGRESS":
                out["status"] = "SKIP_R2_PROGRESS"
                out["new_atoms"] = last.get("new_atoms", [])
    return out


def _final_state_atoms(ir, target: str, workdir: Path) -> set | None:
    
    state_path = workdir / "epochs" / "global_state.json"
    if not state_path.exists():
        return None
    try:
        from stateforge.core.ir import ProgramIR
        from stateforge.solving.state_seed_injector import reached_state_atoms
        return reached_state_atoms(
            ProgramIR.from_json(ir), Path(target),
            json.loads(state_path.read_text(encoding="utf-8")))
    except Exception:                          
        return None
def _final_verified_state_atoms(workdir: Path) -> set | None:
    
    state_path = workdir / "epochs" / "global_state.json"
    if not state_path.exists():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if "state_evidence" not in state:
            return None
        return _verified_state_atoms(state)
    except Exception:                          
        return None
def run_epochs(target: str, ir: str, workdir: Path, seconds_per_epoch: float,
               epochs: int, seed: int, group: str, mode: str,
               use_feedback: bool, t0: float | None = None,
               policy: str = "reinjection", state_trigger: str = "r2",
               state_injector=None) -> dict:
    
    t0 = t0 if t0 is not None else time.monotonic()
    workdir.mkdir(parents=True, exist_ok=True)
    corpus_dir = workdir / "lf_corpus"
    corpus_dir.mkdir(exist_ok=True)

    
    stall_tracker = None
    if policy == "llm":
        from stateforge.solving.stall_tracker import StallTracker
        stall_tracker = StallTracker(stall_window=2, max_llm_per_frontier=3)

    prev_blocks = prev_edges = 0        
    last_blocks = last_edges = 0        
    epoch_records = []
    for epoch in range(1, epochs + 1):
        in_dir = corpus_dir if epoch == 1 else workdir / f"corp_in_e{epoch}"
        if epoch > 1:
            in_dir.mkdir(parents=True, exist_ok=True)

        
        boundary = None
        if policy == "llm" and epoch > 1:
            try:
                _inject_llm_between_epochs(
                    ir, workdir, corpus_dir, target,
                    stall_tracker=stall_tracker, epoch_num=epoch,
                    prev_blocks=prev_blocks, prev_edges=prev_edges)
            except Exception as exc:       
                _llm_audit(workdir, {"epoch": epoch, "event": "SEAM_ERROR",
                                     "error": str(exc)})  
        if policy == "state" and epoch > 1:
            try:
                n_inj = _inject_state_seeds_between_epochs(
                    ir, workdir, corpus_dir, target, epoch_num=epoch,
                    trigger=state_trigger, injector=state_injector)
                boundary = _state_boundary(workdir, epoch, n_inj)
            except Exception as exc:        
                _state_audit(workdir, {"epoch": epoch, "event": "SEAM_ERROR",
                                       "error": str(exc)})  
                boundary = {"epoch": epoch, "atoms_reached": None,
                            "injected": 0, "status": "SEAM_ERROR",
                            "error": str(exc)}

        
        
        
        
        if epoch > 1:
            if use_feedback:
                CorpusManager(workdir / "epochs" / "spool").export_seed_dir(
                    in_dir, extra=[corpus_dir])
            else:
                for f in corpus_dir.iterdir():
                    if f.is_file():
                        shutil.copy2(f, in_dir / f.name)

        in_stats = _dir_stats(in_dir)
        start_off = time.monotonic() - t0
        _run_driver(target, ir, in_dir, workdir / "epochs",
                    seconds_per_epoch, mode, seed, group, epoch)
        end_off = time.monotonic() - t0
        if in_dir != corpus_dir:
            for f in in_dir.iterdir():
                if f.is_file():
                    shutil.copy2(f, corpus_dir / f.name)
        rec = _load_epoch_summary(workdir / "epochs", group, epoch)
        rec["wall"] = {"start_offset": round(start_off, 3),
                       "end_offset": round(end_off, 3),
                       "subprocess_seconds": round(end_off - start_off, 3)}
        rec["corpus_in"] = in_stats
        rec["corpus_lf_after"] = _dir_stats(corpus_dir)
        if boundary is not None:              
            rec["state"] = boundary
        epoch_records.append(rec)
        
        
        
        
        
        prev_blocks, prev_edges = last_blocks, last_edges
        last_blocks, last_edges = rec["blocks"], rec["edges"]
    
    totals = {k: sum(r[k] for r in epoch_records) for k in
              ("executions", "exec_seconds", "feedback_seconds",
               "candidates_saved")}
    last = epoch_records[-1]
    result = {"group": group, "mode": mode, "epochs": epochs,
              "seed": seed, "epoch_records": epoch_records,
              "total_executions": totals["executions"],
              "total_exec_seconds": round(totals["exec_seconds"], 3),
              "total_feedback_seconds": round(totals["feedback_seconds"], 3),
              "total_candidates_saved": totals["candidates_saved"],
              "final_blocks": last["blocks"], "final_edges": last["edges"],
              "group_start_offset": round(epoch_records[0]["wall"]["start_offset"], 3),
              "wall_span": round(epoch_records[-1]["wall"]["end_offset"]
                                 - epoch_records[0]["wall"]["start_offset"], 3)}
    if use_feedback and stall_tracker is not None:
        result["stall_summary"] = stall_tracker.summary()
    if use_feedback:
        result["novel_seed_gain"] = _novel_seed_gain(workdir)
        
        
        state_p = workdir / "epochs" / "global_state.json"
        if state_p.exists():
            pf = __import__("json").loads(
                state_p.read_text(encoding="utf-8")).get("portfolio", {})
            result["portfolio_champions"] = len(pf.get("champions", {}))
            result["portfolio_replacements"] = pf.get("replacement_count", 0)
        last_in = epoch_records[-1].get("corpus_in", {})
        lf_files = _dir_stats(corpus_dir)["files"]
        result["corpus_dilution_ratio"] = round(
            max(last_in.get("files", 0) - lf_files, 0) /
            max(last_in.get("files", 0), 1), 3)
    if policy == "state":                     
        result["state_injections_total"] = sum(
            r.get("state", {}).get("injected", 0) for r in epoch_records)
        final = _final_state_atoms(ir, target, workdir)
        if final is not None:
            result["state_atoms_reached"] = len(final)
            result["state_atoms"] = sorted(final)
        final_verified = _final_verified_state_atoms(workdir)   
        if final_verified is not None:
            result["state_atoms_verified"] = len(final_verified)
            result["state_atoms_verified_list"] = sorted(final_verified)
    (workdir / "group_summary.json").write_text(
        json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    return result
