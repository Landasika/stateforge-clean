from __future__ import annotations
import os
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4] / "external" / "BenchmarkPython"
sys.path.insert(0, str(REPO))
os.chdir(REPO)

from app import app as APP  

CLIENT = APP.test_client()


def _sample_rules(n: int = 24) -> list[tuple[str, str]]:
    rules = sorted(
        (r.rule, sorted(r.methods - {"HEAD", "OPTIONS"})[0] if r.methods else "GET")
        for r in APP.url_map.iter_rules()
        if r.rule.startswith("/benchmark/") and "<" not in r.rule
    )
    if len(rules) > n:                            
        stride = len(rules) / n
        rules = [rules[int(i * stride)] for i in range(n)]
    return [(m, p) for p, m in rules] + [("GET", "/"), ("GET", "/redirected")]


ROUTES = _sample_rules()


def smoke() -> list[tuple[str, int]]:
    out = []
    for method, path in ROUTES:
        try:
            r = CLIENT.get(path) if method in ("GET", "HEAD") else CLIENT.post(path)
            out.append((f"{method} {path}", r.status_code))
        except Exception as exc:                 
            out.append((f"{method} {path}", f"EXC:{type(exc).__name__}"))
    return out


if __name__ == "__main__":
    results = smoke()
    ok = sum(1 for _, s in results if isinstance(s, int) and s < 500)
    n_rules = len(list(APP.url_map.iter_rules()))
    print(f"smoke: {ok}/{len(results)} non-5xx (url_map rules={n_rules})")
    for route, status in results:
        print(f"  {status!s:>4}  {route}")
