from __future__ import annotations
import json
import os
from stateforge.targets.vampi.adapter import VAMPI_DIR
os.chdir(VAMPI_DIR)       

from stateforge.targets.vampi.adapter import make_app

APP = make_app(vulnerable=1, token_ttl=600)
CLIENT = APP.test_client()


CLIENT.get("/createdb")
_USER = "admin"          
ROUTES: list[tuple[str, str, str]] = [
    ("GET", "/", "public"),                         
    ("GET", "/users/v1", "public"),
    ("GET", "/users/v1/_debug", "public"),
    ("POST", "/users/v1/register", "public"),
    ("POST", "/users/v1/login", "public"),
    ("GET", "/books/v1", "public"),
    ("POST", "/books/v1", "token"),
    ("GET", f"/users/v1/{_USER}", "public"),
    ("PUT", f"/users/v1/{_USER}/email", "token"),
    ("PUT", f"/users/v1/{_USER}/password", "token"),
    ("GET", "/books/v1/somebook", "public"),
    ("GET", "/me", "token"),
    ("GET", "/createdb", "public"),                 
    ("GET", "/openapi.json", "public"),
]

_TOKEN = None
_r = CLIENT.post("/users/v1/login",
                 data=json.dumps({"username": _USER, "password": "pass1"}),
                 content_type="application/json")
try:
    _TOKEN = (json.loads(_r.data).get("auth_token")
              or json.loads(_r.data).get("token")) if _r.status_code == 200 else None
except Exception:
    _TOKEN = None

_POST_BODIES = {
    "login": {"username": "admin", "password": "pass1"},
    "/register": {"username": "probe", "password": "probe",
                  "email": "probe@vampi.io"},
    "/books/v1": {"title": "probe-book", "author": "probe",
                  "isbn": "0000000000000"},
}


def smoke() -> list[tuple[str, int]]:
    out = []
    for method, path, auth in ROUTES:
        try:
            headers = {"Authorization": f"Bearer {_TOKEN}"} if auth == "token" and _TOKEN else {}
            body = next((v for k, v in _POST_BODIES.items()
                         if path.endswith(k)), None) if method != "GET" else None
            if method == "GET":
                r = CLIENT.get(path, headers=headers)
            else:
                fn = CLIENT.put if method == "PUT" else CLIENT.post
                r = fn(path, data=json.dumps(body) if body else {},
                       content_type="application/json", headers=headers)
            out.append((f"{method} {path}", r.status_code))
        except Exception as exc:                     
            out.append((f"{method} {path}", f"EXC:{type(exc).__name__}"))
    return out


if __name__ == "__main__":
    results = smoke()
    ok = sum(1 for _, s in results if isinstance(s, int) and s < 500)
    print(f"smoke: {ok}/{len(results)} non-5xx token={'yes' if _TOKEN else 'no'}")
    for route, status in results:
        print(f"  {status!s:>4}  {route}")
