from __future__ import annotations
from dataclasses import dataclass, field
from stateforge.runtime.mapper import MappedTrace
@dataclass
class Observation:
    

    blocks: set[str] = field(default_factory=set)     
    edges: set[tuple[str, str]] = field(default_factory=set)  
    new_blocks: set[str] = field(default_factory=set)  
    new_edges: set[tuple[str, str]] = field(default_factory=set)  

    @property
    def score(self) -> int:
        return len(self.new_blocks) + len(self.new_edges)
    @property
    def interesting(self) -> bool:
        return self.score > 0


class StructuralFeedback:
    

    def __init__(self) -> None:
        self._global_blocks: set[str] = set()
        self._global_edges: set[tuple[str, str]] = set()

    
    @property
    def global_blocks(self) -> set[str]:
        return set(self._global_blocks)

    @property
    def global_edges(self) -> set[tuple[str, str]]:
        return set(self._global_edges)
    def update_global_coverage(self, blocks: set[str],
                                edges: set[tuple[str, str]]) -> None:
        
        self._global_blocks |= blocks
        self._global_edges |= edges

    
    @staticmethod
    def evidence(trace: MappedTrace) -> tuple[set[str], set[tuple[str, str]]]:
        
        blocks = set(trace.block_hits)
        edges = set(trace.edge_kinds)          
        return blocks, edges

    def observe(self, trace: MappedTrace) -> Observation:
        
        blocks, edges = self.evidence(trace)
        return Observation(
            blocks=blocks, edges=edges,
            new_blocks=blocks - self._global_blocks,
            new_edges=edges - self._global_edges,
        )
