from __future__ import annotations
import http.client
import importlib.util
import sys
import threading
from pathlib import Path
REPO = Path(__file__).resolve().parents[2] / "dsvw"   

_spec = importlib.util.spec_from_file_location("dsvw_app", REPO / "dsvw.py")
dsvw = importlib.util.module_from_spec(_spec)
sys.modules["dsvw_app"] = dsvw
_spec.loader.exec_module(dsvw)

dsvw.init()                                   

_server = dsvw.ThreadingServer(("127.0.0.1", 0), dsvw.ReqHandler)
_PORT = _server.server_address[1]
threading.Thread(target=_server.serve_forever, daemon=True).start()

_CONN = http.client.HTTPConnection("127.0.0.1", _PORT, timeout=10)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/"),
    ("GET", "/?id=1"),
    ("GET", "/?id=2"),
    ("GET", "/?id=3"),
    ("GET", "/?v=probe"),
    ("GET", "/?name=admin"),
    ("GET", "/?name=nope"),
    ("GET", "/?comment="),                    
    ("GET", "/?comment=hello-from-harness"),  
    ("GET", "/?size=2"),
    ("GET", "/?redir=/"),
    ("GET", "/?tmpl={0}"),
    ("GET", "/?charset=utf8"),
    ("GET", "/users.json"),
    ("GET", "/?callback=cb"),
    ("GET", "/users.json?callback=cb"),
    ("GET", "/login?username=admin&password=admin"),
    ("GET", "/login?username=admin&password=wrong"),
    ("GET", "/login?username=nope&password=x"),
    ("GET", "/nonexistent"),                  
    ("GET", "/?id=1&charset=utf8"),
    ("GET", "/?v=probe&name=admin"),
]


def _request(method: str, path: str) -> int:
    _CONN.request(method, path)
    r = _CONN.getresponse()
    r.read()
    return r.status


def smoke() -> list[tuple[str, int]]:
    out = []
    for method, path in ROUTES:
        try:
            out.append((f"{method} {path}", _request(method, path)))
        except Exception as exc:              
            out.append((f"{method} {path}", f"EXC:{type(exc).__name__}"))
    return out


if __name__ == "__main__":
    results = smoke()
    ok = sum(1 for _, s in results if isinstance(s, int) and s < 500)
    print(f"smoke: {ok}/{len(results)} non-5xx (port={_PORT})")
    for route, status in results:
        print(f"  {status!s:>4}  {route}")
