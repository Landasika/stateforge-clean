from __future__ import annotations
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class CorpusEntryMeta:
    input_id: str            
    epoch: int
    discovered_blocks: int
    discovered_edges: int
    new_blocks: int
    new_edges: int
    structural_score: int
    saved_at: float
    
    distance: int | None = None
    nearest_frontier: str | None = None
    interesting_reason: str = "new_structure"
    origin: str = "NATIVE"            
    parent_seed_id: str | None = None
    llm_attempt_id: str | None = None
class CorpusManager:
    

    def __init__(self, spool_dir: str | Path):
        self.spool = Path(spool_dir)
        self.seeds_dir = self.spool / "seeds"
        self.meta_path = self.spool / "meta.jsonl"
        self.seeds_dir.mkdir(parents=True, exist_ok=True)
        self._seen_hashes: set[str] = set()
        self._load_existing()

    def _load_existing(self) -> None:
        if self.meta_path.exists():
            for line in self.meta_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._seen_hashes.add(json.loads(line)["input_id"])

    @staticmethod
    def content_id(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()[:16]

    def save(self, data: bytes, epoch: int, new_blocks: int, new_edges: int,
             discovered_blocks: int, discovered_edges: int,
             distance: int | None = None, nearest_frontier: str | None = None,
             interesting_reason: str = "new_structure",
             origin: str = "NATIVE", parent_seed_id: str | None = None,
             llm_attempt_id: str | None = None) -> str | None:
        
        cid = self.content_id(data)
        if cid in self._seen_hashes:
            return None
        self._seen_hashes.add(cid)
        score = new_blocks + new_edges
        (self.seeds_dir / cid).write_bytes(data)
        meta = CorpusEntryMeta(cid, epoch, discovered_blocks, discovered_edges,
                               new_blocks, new_edges, score, time.time(),
                               distance, nearest_frontier, interesting_reason,
                               origin, parent_seed_id, llm_attempt_id)
        with self.meta_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(meta), ensure_ascii=False) + "\n")
            fh.flush()
        return cid

    def entries(self) -> list[CorpusEntryMeta]:
        if not self.meta_path.exists():
            return []
        return [CorpusEntryMeta(**json.loads(line))
                for line in self.meta_path.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def export_seed_dir(self, out_dir: str | Path, extra: list[Path] | None = None
                        ) -> int:
        
        import shutil
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        count = 0
        for seed in self.seeds_dir.iterdir():
            shutil.copy2(seed, out / seed.name)
            count += 1
        for src_dir in extra or []:
            if not Path(src_dir).exists():
                continue
            for seed in Path(src_dir).iterdir():
                if seed.is_file() and not (out / seed.name).exists():
                    shutil.copy2(seed, out / seed.name)
                    count += 1
        return count
