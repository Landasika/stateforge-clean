import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3] / "external" / "realworld-django-ninja"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DEBUG", "true")
sys.path.insert(0, str(REPO))

import django  
django.setup()

from django.conf import settings  
settings.ALLOWED_HOSTS.append("testserver")

from django.test import Client  
from django.core.management import call_command  


_DB = REPO / f".sf_rw_{os.getpid()}.sqlite3"
settings.DATABASES["default"]["NAME"] = str(_DB)
if not _DB.exists():
    call_command("migrate", verbosity=0, interactive=False, run_syncdb=True)

_CLIENT = Client()


_TOKEN = None
_r = _CLIENT.post("/api/users", data=json.dumps({
    "user": {"email": "fuzz@rw.com", "password": "Fuzz1234!",
             "username": "fuzzer"}}), content_type="application/json")
if _r.status_code == 201:
    _TOKEN = json.loads(_r.content)["user"]["token"]
    _AUTH = {"Authorization": f"Token {_TOKEN}"}
else:
    _AUTH = {}


def target(data: bytes) -> None:
    try:
        seed = json.loads(data) if data else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    if not isinstance(seed, dict):
        return

    method = str(seed.get("method", "GET")).upper()
    path = str(seed.get("path", "/api/tags"))
    body = seed.get("body")
    headers = {**_AUTH, **(seed.get("headers") or {})}

    
    extra = {f"HTTP_{k.replace('-', '_').upper()}": v
             for k, v in headers.items()}
    try:
        if method == "GET":
            _CLIENT.get(path, **extra)
        elif body is not None:
            _CLIENT.generic(method, path, data=json.dumps(body),
                            content_type="application/json", **extra)
        else:
            _CLIENT.generic(method, path, **extra)
    except Exception:                        
        pass
