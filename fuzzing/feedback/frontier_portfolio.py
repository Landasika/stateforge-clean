from __future__ import annotations
from dataclasses import dataclass, field
@dataclass
class ChampionRecord:
    input_id: str
    distance: int
    epoch: int
    frontier_version: int


@dataclass
class PortfolioEvent:
    kind: str                       
    frontier: str
    input_id: str | None = None
    old_distance: int | None = None
    new_distance: int | None = None
    epoch: int = 0


class FrontierPortfolio:
    def __init__(self) -> None:
        self.champions: dict[str, ChampionRecord] = {}
        self.events: list[PortfolioEvent] = []
        self.replacement_count = 0

    
    def challenge(self, frontier: str, distance: int, input_id: str,
                  epoch: int, version: int) -> tuple[bool, str]:
        
        cur = self.champions.get(frontier)
        if cur is None:
            self.champions[frontier] = ChampionRecord(input_id, distance,
                                                      epoch, version)
            self.events.append(PortfolioEvent("champion_new", frontier,
                                              input_id, None, distance, epoch))
            return True, "frontier_champion"
        if distance < cur.distance:
            self.champions[frontier] = ChampionRecord(input_id, distance,
                                                      epoch, version)
            self.replacement_count += 1
            self.events.append(PortfolioEvent(
                "champion_replace", frontier, input_id,
                cur.distance, distance, epoch))
            return True, "frontier_progress"
        return False, "none"

    
    def retire(self, active_frontiers: set[str]) -> None:
        for f in list(self.champions):
            if f not in active_frontiers:
                rec = self.champions.pop(f)
                self.events.append(PortfolioEvent(
                    "champion_retire", f, rec.input_id, rec.distance,
                    None, rec.epoch))

    def drain_events(self) -> list[PortfolioEvent]:
        out, self.events = self.events, []
        return out

    def state(self) -> dict:
        return {"champions": {f: vars(r) for f, r in self.champions.items()},
                "replacement_count": self.replacement_count}

    def load_state(self, state: dict) -> None:
        self.champions = {f: ChampionRecord(**r)
                          for f, r in state.get("champions", {}).items()}
        self.replacement_count = state.get("replacement_count", 0)
