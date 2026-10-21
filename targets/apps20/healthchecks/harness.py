from __future__ import annotations
import json
import os
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4] / "external" / "healthchecks"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hc.settings")
os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("ALLOWED_HOSTS", "testserver,localhost")
_DB = Path(os.environ.get("SF_DB", REPO / f".sf_db_{os.getpid()}.sqlite3"))
os.environ["DB_NAME"] = str(_DB)

sys.path.insert(0, str(REPO))

import django  

django.setup()

from django.core.management import call_command  
from django.test import Client  

call_command("migrate", verbosity=0, interactive=False, run_syncdb=True)


from hc.accounts.models import Profile, Project, User  
from hc.api.models import Check  

_USER, _PASS = "probe@example.org", "passw0rd!"
user = User(username="probe", email=_USER)
user.set_password(_PASS)
user.save()
Profile.objects.for_user(user)                    
project = Project(owner=user)
project.badge_key = user.username
project.save()
check = Check(project=project)
check.name = "Probe Check"
check.slug = "probe-check"
check.save()
_rw = _ro = None
try:
    _rw = project.set_api_key()                    
    _ro = project.set_api_key_readonly()
    project.save()
except Exception:
    pass

CLIENT = Client()
CLIENT.login(username=_USER, password=_PASS)

CODE = str(check.code)
PROJECT_CODE = str(project.code)
API_KEY = _rw or ""


ROUTES: list[tuple[str, str, str]] = [
    ("GET", "/", "public"),
    ("GET", "/docs/", "public"),
    ("GET", "/docs/cron/", "public"),
    ("GET", "/accounts/login/", "public"),
    ("POST", "/accounts/login/", "auth-form"),
    ("GET", "/tv/", "session"),
    ("GET", "/projects/menu/", "session"),
    ("GET", f"/projects/{PROJECT_CODE}/checks/", "session"),
    ("POST", f"/projects/{PROJECT_CODE}/checks/add/", "session"),
    ("GET", f"/projects/{PROJECT_CODE}/integrations/", "session"),
    ("GET", "/accounts/profile/", "session"),
    ("GET", f"/projects/{PROJECT_CODE}/settings/", "session"),
    ("GET", f"/projects/{PROJECT_CODE}/badges/", "session"),
    ("GET", f"/checks/{CODE}/status/", "session"),
    ("GET", f"/checks/{CODE}/details/", "session"),
    
    ("GET", f"/ping/{CODE}", "capability"),
    ("GET", f"/ping/{CODE}/fail", "capability"),
    ("GET", f"/ping/{CODE}/start", "capability"),
    ("GET", f"/ping/{CODE}/log", "capability"),
    ("GET", f"/ping/{CODE}/1", "capability"),
    
    ("GET", "/api/v3/checks/", "api-key"),
    ("POST", "/api/v3/checks/", "api-key"),
    ("GET", f"/api/v3/checks/{CODE}", "api-key"),
    ("POST", f"/api/v3/checks/{CODE}/pause", "api-key"),
    ("POST", f"/api/v3/checks/{CODE}/resume", "api-key"),
]

_POST_BODIES = {
    "/checks/add/": {"name": "from-harness", "tags": "probe", "kind": "simple",
                     "timeout": 3600, "grace": 60, "tz": "UTC", "schedule": ""},
    "/api/v3/checks/": {"name": "api-check", "slug": "api-check", "timeout": 60},
}


def smoke() -> list[tuple[str, int]]:
    
    out = []
    for method, path, auth in ROUTES:
        try:
            headers = {}
            if auth == "api-key" and API_KEY:
                headers["X-Api-Key"] = API_KEY
            extra = {f"HTTP_{k.replace('-', '_').upper()}": v
                     for k, v in headers.items()}
            body = None
            if method == "POST":
                body = next((v for k, v in _POST_BODIES.items()
                             if path.endswith(k)), None)
            if method == "POST":
                if path.startswith("/api/"):
                    r = CLIENT.post(path, data=json.dumps(body) if body else "",
                                    content_type="application/json", **extra)
                else:                             
                    r = CLIENT.post(path, data=body or {}, **extra)
            else:
                r = CLIENT.get(path, **extra)
            out.append((f"{method} {path}", r.status_code))
        except Exception as exc:                     
            out.append((f"{method} {path}", f"EXC:{type(exc).__name__}"))
    return out


if __name__ == "__main__":
    results = smoke()
    ok = sum(1 for _, s in results if isinstance(s, int) and s < 500)
    print(f"smoke: {ok}/{len(results)} non-5xx")
    for route, status in results:
        print(f"  {status!s:>4}  {route}")
