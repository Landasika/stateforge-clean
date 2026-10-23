from __future__ import annotations

import json
import os
import sys
from pathlib import Path

TARGET_DIR = Path(__file__).resolve().parent / "app"

os.environ.setdefault("vulnerable", "1")
os.environ.setdefault("tokentimetolive", "600")
if str(TARGET_DIR) not in sys.path:
    sys.path.insert(0, str(TARGET_DIR))
os.chdir(TARGET_DIR)

import config

APP = config.vuln_app.app
CLIENT = APP.test_client()
CLIENT.get("/createdb")

_USER = "admin"
_r = CLIENT.post(
    "/users/v1/login",
    data=json.dumps({"username": _USER, "password": "pass1"}),
    content_type="application/json",
)
try:
    body = json.loads(_r.data)
    _TOKEN = body.get("auth_token") or body.get("token")
except Exception:
    _TOKEN = None

ROUTES = [
    ("GET", "/"),
    ("GET", "/users/v1"),
    ("GET", "/users/v1/_debug"),
    ("POST", "/users/v1/register"),
    ("POST", "/users/v1/login"),
    ("GET", "/books/v1"),
    ("POST", "/books/v1"),
    ("GET", f"/users/v1/{_USER}"),
    ("PUT", f"/users/v1/{_USER}/email"),
    ("PUT", f"/users/v1/{_USER}/password"),
    ("GET", "/books/v1/somebook"),
    ("GET", "/me"),
    ("GET", "/createdb"),
    ("GET", "/openapi.json"),
]

_POST_BODIES = {
    "login": {"username": "admin", "password": "pass1"},
    "register": {"username": "probe", "password": "probe",
                 "email": "probe@vampi.io"},
    "books/v1": {"title": "probe-book", "author": "probe",
                 "isbn": "0000000000000"},
}


def smoke():
    results = []
    for method, path in ROUTES:
        headers = ({"Authorization": f"Bearer {_TOKEN}"}
                   if _TOKEN and path in ("/me", "/books/v1",
                                          f"/users/v1/{_USER}/email",
                                          f"/users/v1/{_USER}/password")
                   else {})
        body = None
        for suffix, candidate in _POST_BODIES.items():
            if path.endswith(suffix):
                body = candidate
                break
        try:
            if method == "GET":
                response = CLIENT.get(path, headers=headers)
            elif method == "PUT":
                response = CLIENT.put(
                    path,
                    data=json.dumps(body) if body is not None else "{}",
                    content_type="application/json",
                    headers=headers)
            else:
                response = CLIENT.post(
                    path,
                    data=json.dumps(body) if body is not None else "{}",
                    content_type="application/json",
                    headers=headers)
            results.append((f"{method} {path}", response.status_code))
        except Exception as exc:
            results.append((f"{method} {path}",
                            f"EXC:{type(exc).__name__}:{exc}"))
    return results


if __name__ == "__main__":
    results = smoke()
    ok = sum(1 for _, status in results
             if isinstance(status, int) and status < 500)
    print(f"smoke: {ok}/{len(results)} non-5xx token={'yes' if _TOKEN else 'no'}")
    for route, status in results:
        print(f"  {status!s:>4}  {route}")
