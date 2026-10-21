from __future__ import annotations
import json
import subprocess
import time
from pathlib import Path

ANOTA_PY = Path(__file__).parents[2] / "anota" / "ANOTA" / "ANOTA-interpreter" / "python"


_ENTRY_NAMES = {"app.py", "manage.py", "factory.py", "wsgi.py", "asgi.py", "config.py"}
_ENTRY_HINTS = ("views", "routes", "controllers", "urls", "api", "handlers")
_SKIP_DIRS = {"tests", "__pycache__", "migrations", "docs", "node_modules", ".git"}


def detect_entries(root: Path, max_entries: int = 12) -> list[Path]:
    
    primary: list[Path] = []
    secondary: list[Path] = []
    for py in sorted(root.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in py.parts):
            continue
        if py.name in _ENTRY_NAMES:
            primary.append(py)
        elif any(h in py.name.lower() for h in _ENTRY_HINTS):
            secondary.append(py)
    
    primary.sort(key=lambda p: (p.name == "__init__.py", len(p.parts)))
    return (primary + secondary)[:max_entries]


def _ensure_pycg_importable(python: Path) -> None:
    probe = subprocess.run(
        [str(python), "-c", "import pycg"], capture_output=True, timeout=30)
    if probe.returncode != 0:
        site = subprocess.run(
            [str(python), "-c", "import site;print(site.getsitepackages()[0])"],
            capture_output=True, text=True, timeout=30).stdout.strip()
        link = Path(site) / "pycg"
        if not link.exists() and (Path(site) / "PyCG").exists():
            link.symlink_to("PyCG")


def run_pycg(entry: Path, python: Path = ANOTA_PY, timeout: int = 120) -> dict | None:
    
    entry = Path(entry).resolve()
    _ensure_pycg_importable(python)
    out = entry.parent / f".pycg-{entry.stem}.json"
    try:
        r = subprocess.run(
            [str(python), "-m", "PyCG", str(entry), "-o", str(out)],
            capture_output=True, timeout=timeout, cwd=str(entry.parent.parent),
        )
        if r.returncode == 0 and out.exists():
            return json.loads(out.read_text(encoding="utf-8"))
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        pass
    finally:
        out.unlink(missing_ok=True)
    return None


def merge_callgraphs(parts: list[dict]) -> dict:
    
    merged: dict[str, list[str]] = {}
    for part in parts:
        for k, v in part.items():
            bucket = merged.setdefault(k, [])
            bucket.extend(x for x in v if x not in bucket)
    return merged


def build_callgraph(root: str | Path, cache_path: str | Path | None = None,
                    max_entries: int = 12, force: bool = False,
                    python: Path = ANOTA_PY) -> tuple[dict, list[str]]:
    
    root = Path(root)
    cache = Path(cache_path) if cache_path else root / ".pycg-callgraph.json"
    if cache.exists() and not force and time.time() - cache.stat().st_mtime < 86400:
        data = json.loads(cache.read_text(encoding="utf-8"))
        return data.get("graph", {}), data.get("gaps", [])
    entries = detect_entries(root, max_entries)
    parts: list[dict] = []
    gaps: list[str] = []
    for e in entries:
        part = run_pycg(e, python=python)
        if part:
            parts.append(part)
        else:
            gaps.append(str(e))
    graph = merge_callgraphs(parts)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"graph": graph, "gaps": gaps,
                                 "entries": [str(e) for e in entries],
                                 "ok": len(parts), "generated": time.strftime("%F %T")}),
                     encoding="utf-8")
    return graph, gaps
