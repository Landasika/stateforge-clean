from __future__ import annotations
from dataclasses import dataclass, field
W_WINDOW = 2000            


@dataclass
class PlateauState:
    status: str = "RUNNING"             
    window_start_exec: int = 0
    window_start_blocks: int = 0
    window_start_edges: int = 0
    window_start_crossings: int = 0
    stagnated_since: int | None = None  


class PlateauDetector:
    
    def __init__(self, window: int = W_WINDOW):
        self.window = window
        self._state = PlateauState()
    @property
    def status(self) -> str:
        return self._state.status

    def observe(self, total_executions: int, total_blocks: int,
                total_edges: int, total_crossings: int) -> str:
        s = self._state
        if s.status == "RUNNING":
            in_window = total_executions - s.window_start_exec
            if in_window >= self.window:
                d_blocks = total_blocks - s.window_start_blocks
                d_edges = total_edges - s.window_start_edges
                d_cross = total_crossings - s.window_start_crossings
                if d_blocks == 0 and d_edges == 0 and d_cross == 0:
                    s.status = "STAGNATED"
                    s.stagnated_since = total_executions
                else:
                    
                    s.window_start_exec = total_executions
                    s.window_start_blocks = total_blocks
                    s.window_start_edges = total_edges
                    s.window_start_crossings = total_crossings
        elif s.status == "STAGNATED":
            
            if total_crossings > s.window_start_crossings:
                s.status = "RUNNING"
                s.window_start_exec = total_executions
                s.window_start_blocks = total_blocks
                s.window_start_edges = total_edges
                s.window_start_crossings = total_crossings
                s.stagnated_since = None
        return s.status
