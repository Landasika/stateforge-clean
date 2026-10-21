from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
@dataclass
class FrontierStatus:
    edge: tuple[str, str]
    first_seen_epoch: int
    last_seen_epoch: int
    epochs_stalled: int = 0
    llm_attempted: bool = False


class StallTracker:
    

    def __init__(self, stall_window: int = 2, max_llm_per_frontier: int = 3):
        self.stall_window = stall_window
        self.max_llm = max_llm_per_frontier
        self.frontiers: dict[tuple[str, str], FrontierStatus] = {}
        self.llm_counts: dict[tuple[str, str], int] = {}
        self.total_llm_calls = 0
        self.history: list[dict] = []          

    def observe_epoch(self, epoch: int,
                     active_frontiers: set[tuple[str, str]],
                     new_blocks: int, new_edges: int) -> list[tuple[str, str]]:
        
        
        for edge in active_frontiers:
            if edge not in self.frontiers:
                self.frontiers[edge] = FrontierStatus(
                    edge, epoch, epoch)
            else:
                fs = self.frontiers[edge]
                fs.last_seen_epoch = epoch
                if new_blocks == 0 and new_edges == 0:
                    fs.epochs_stalled += 1
                else:
                    fs.epochs_stalled = 0          

        
        for edge in list(self.frontiers):
            if edge not in active_frontiers:
                del self.frontiers[edge]

        
        to_inject = []
        for edge, fs in self.frontiers.items():
            if (fs.epochs_stalled >= self.stall_window
                    and not fs.llm_attempted):
                count = self.llm_counts.get(edge, 0)
                if count < self.max_llm:
                    to_inject.append(edge)
                    fs.llm_attempted = True

        self.history.append({
            "epoch": epoch,
            "active_frontiers": len(active_frontiers),
            "new_blocks": new_blocks, "new_edges": new_edges,
            "stalled": len([f for f in self.frontiers.values()
                            if f.epochs_stalled >= self.stall_window]),
            "injecting": len(to_inject),
        })
        return to_inject
    def mark_injected(self, edge: tuple[str, str]):
        self.llm_counts[edge] = self.llm_counts.get(edge, 0) + 1
        self.total_llm_calls += 1
        
        if edge in self.frontiers:
            self.frontiers[edge].llm_attempted = False

    def summary(self) -> dict:
        return {
            "total_frontiers_seen": len(self.frontiers),
            "total_llm_calls": self.total_llm_calls,
            "llm_per_frontier": {f"{e[0]}->{e[1]}": c
                                 for e, c in self.llm_counts.items()},
            "history": self.history,
        }
