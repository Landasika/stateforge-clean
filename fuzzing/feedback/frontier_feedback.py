from __future__ import annotations
from dataclasses import dataclass, field
from stateforge.core.ir import ProgramIR
from stateforge.runtime.mapper import MappedTrace
from stateforge.fuzzing.feedback.distance_oracle import DistanceOracle
from stateforge.fuzzing.feedback.frontier_portfolio import FrontierPortfolio
from stateforge.fuzzing.feedback.frontier_tracker import FrontierTracker
from stateforge.fuzzing.feedback.structural import StructuralFeedback


@dataclass
class FrontierObservation:
    new_blocks: int = 0
    new_edges: int = 0
    distance: int | None = None            
    nearest_frontier: str | None = None
    proximity: float = 0.0
    score: float = 0.0
    interesting: bool = False
    reason: str = "none"                   
    frontier_version: int = 0
    edge_frontier_count: int = 0


class FrontierDirectedFeedback:
    def __init__(self, ir: ProgramIR):
        self.ir = ir
        self.novelty = StructuralFeedback()
        self.tracker = FrontierTracker(ir)
        self.oracle = DistanceOracle(ir)
        self.portfolio = FrontierPortfolio()       
        self._observe_calls = 0

    
    def export_state(self) -> dict:
        state = self.tracker.state()
        state["portfolio"] = self.portfolio.state()
        return state

    def load_state(self, state: dict) -> None:
        blocks = set(state.get("covered_blocks", []))
        edges = {tuple(e) for e in state.get("covered_edges", [])}
        self.novelty.update_global_coverage(blocks, edges)   
        self.tracker.covered_blocks, self.tracker.covered_edges = set(blocks), set(edges)
        self.tracker._recompute()
        self.tracker.version = state.get("version", 0) + 1
        self.portfolio.load_state(state.get("portfolio", {}))
        self.oracle.rebuild(self.tracker.edge_frontiers, self.tracker.version)

    def observe(self, trace: MappedTrace,
                input_id: str = "") -> FrontierObservation:
        
        obs = self.novelty.observe(trace)               
        self.oracle.rebuild(self.tracker.edge_frontiers, self.tracker.version)
        d, near = self.oracle.distance(set(trace.block_hits))
        proximity = 1.0 / (1 + d) if d is not None else 0.0
        obs31 = FrontierObservation(
            new_blocks=len(obs.new_blocks), new_edges=len(obs.new_edges),
            distance=d, nearest_frontier=near, proximity=proximity,
            frontier_version=self.tracker.version,
            edge_frontier_count=len(self.tracker.edge_frontiers))
        obs31.score = obs31.new_blocks + obs31.new_edges + proximity

        if obs31.new_blocks or obs31.new_edges:
            obs31.interesting, obs31.reason = True, \
                "new_blocks" if obs31.new_blocks else "new_edges"
        elif near is not None and d is not None:
            kept, reason = self.portfolio.challenge(          
                near, d, input_id, self._current_epoch, self.tracker.version)
            if kept:
                obs31.interesting, obs31.reason = True, reason
        return obs31

    _current_epoch = 0
    def commit(self, trace: MappedTrace, kept: bool) -> None:
        
        blocks, edges = self.novelty.evidence(trace)
        self.novelty.update_global_coverage(blocks, edges)
        grew = self.tracker.update(blocks, edges)
        if grew:
            self.oracle.rebuild(self.tracker.edge_frontiers,
                                self.tracker.version)
            self.portfolio.retire({f"{u}->{v}"                 
                                   for (u, v) in self.tracker.edge_frontiers})
