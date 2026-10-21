from __future__ import annotations
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3] / "external" / "realworld-django-ninja"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DEBUG", "true")
sys.path.insert(0, str(REPO))

import django  

_DB = Path(os.environ.get("SF_DB", REPO / f".sf_db_{os.getpid()}.sqlite3"))
os.environ["SF_DB_MIGRATED"] = "0"
django.setup()
from django.conf import settings  

settings.DATABASES["default"]["NAME"] = str(_DB)

from django.core.management import call_command  
from django.test import Client  

call_command("migrate", verbosity=0, interactive=False, run_syncdb=True)
os.environ["SF_DB_MIGRATED"] = "1"
_CLIENT = Client()
_USER = "probe1"
_PASS = "passw0rd!"
_EMAIL = "probe1@example.com"
r = _CLIENT.post("/api/users", data=json.dumps({"user": {
    "email": _EMAIL, "password": _PASS, "username": _USER}}),
    content_type="application/json")
_token = json.loads(r.content)["user"]["token"] if r.status_code == 201 else None
r = _CLIENT.post("/api/articles", data=json.dumps({"article": {
    "title": "SeedArticle", "body": "b", "description": "d", "tagList": ["t"]}}),
    content_type="application/json",
    **({"HTTP_AUTHORIZATION": f"Token {_token}"} if _token else {}))
_SLUGS = ["seedarticle"]
if r.status_code == 201:
    _SLUGS.insert(0, json.loads(r.content)["article"]["slug"])

ROUTES = [
    ("GET", "/api/tags"),
    ("GET", "/api/articles"),
    ("GET", "/api/articles/feed"),
    ("GET", "/api/articles/{slug}"),
    ("POST", "/api/articles"),
    ("PUT", "/api/articles/{slug}"),
    ("DELETE", "/api/articles/{slug}"),
    ("POST", "/api/articles/{slug}/favorite"),
    ("DELETE", "/api/articles/{slug}/favorite"),
    ("GET", "/api/articles/{slug}/comments"),
    ("POST", "/api/articles/{slug}/comments"),
    ("DELETE", "/api/articles/{slug}/comments/{id}"),
    ("GET", "/api/profiles/{username}"),
    ("POST", "/api/profiles/{username}/follow"),
    ("DELETE", "/api/profiles/{username}/follow"),
    ("GET", "/api/user"),
    ("PUT", "/api/user"),
    ("POST", "/api/users"),
    ("POST", "/api/users/login"),
    ("GET", "/api/articles?tag=t&limit=5&offset=0"),   
]
_METHODS = ("GET", "POST", "PUT", "DELETE")


def target(data: bytes) -> None:
    if not data:
        return
    route_i = data[0] % len(ROUTES)
    method = _METHODS[data[1] % len(_METHODS)] if len(data) > 1 else "GET"
    use_auth = len(data) > 2 and data[2] & 1
    default_method, path_tpl = ROUTES[route_i]
    body = data[3:] if len(data) > 3 else b""
    slug = _SLUGS[data[1] % len(_SLUGS)] if _SLUGS else "seedarticle"
    path = path_tpl.format(slug=slug, username=_USER, id=1)
    headers = {"HTTP_AUTHORIZATION": f"Token {_token}"} \
        if use_auth and _token else {}
    try:
        resp = _CLIENT.generic(method, path, data=body,
                               content_type="application/json", **headers)
        if method == "POST" and "/api/articles" in path and resp.status_code == 201:
            try:
                _SLUGS.insert(0, json.loads(resp.content)["article"]["slug"])
            except Exception:            
                pass
    except Exception:                    
        pass
