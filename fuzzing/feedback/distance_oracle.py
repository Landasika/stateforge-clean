from __future__ import annotations
from collections import deque
from stateforge.core.ir import ProgramIR


class DistanceOracle:
    def __init__(self, ir: ProgramIR):
        self._reverse: dict[str, list[str]] = {}
        for edge in ir.edges:
            self._reverse.setdefault(edge.dst, []).append(edge.src)
        self._version: int | None = None
        self._dist: dict[str, int] = {}
        self._nearest: dict[str, str] = {}
        self.unreachable_count = 0            

    def rebuild(self, edge_frontiers: list[tuple[str, str]], version: int) -> None:
        if version == self._version:
            return
        self._version = version
        self._dist, self._nearest = {}, {}
        queue = deque()
        for (u, v) in edge_frontiers:          
            self._dist[u] = 0
            self._nearest[u] = f"{u}->{v}"
            queue.append(u)
        while queue:
            node = queue.popleft()
            d = self._dist[node]
            for parent in self._reverse.get(node, []):
                if parent not in self._dist:
                    self._dist[parent] = d + 1
                    self._nearest[parent] = self._nearest[node]
                    queue.append(parent)

    def distance(self, blocks: set[str]) -> tuple[int | None, str | None]:
        
        best_d, best_f = None, None
        for b in blocks:
            d = self._dist.get(b)
            if d is not None and (best_d is None or d < best_d):
                best_d, best_f = d, self._nearest[b]
        if best_d is None and blocks:
            self.unreachable_count += 1
        return best_d, best_f
