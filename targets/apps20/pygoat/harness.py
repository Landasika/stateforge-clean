from __future__ import annotations
import os
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2] / "pygoat"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pygoat.settings")
sys.path.insert(0, str(REPO))
os.chdir(REPO)

import django  

django.setup()

from django.conf import settings  

_DB = Path(os.environ.get("SF_DB", REPO / f".sf_db_{os.getpid()}.sqlite3"))
settings.DATABASES["default"]["NAME"] = str(_DB)

from django.core.management import call_command  

call_command("migrate", verbosity=0, interactive=False, run_syncdb=True)

_USER, _PASS = "probe", "Passw0rd!"
from django.contrib.auth import get_user_model  

User = get_user_model()
if not User.objects.filter(username=_USER).exists():
    User.objects.create_superuser(_USER, "probe@pygoat.local", _PASS)

from django.test import Client  

CLIENT = Client()
CLIENT.login(username=_USER, password=_PASS)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/"),
    ("GET", "/xss"),
    ("GET", "/xssL"),
    ("GET", "/xssL2"),
    ("GET", "/xssL3"),
    ("GET", "/sql"),
    ("GET", "/sql_lab"),
    ("GET", "/insec_des"),
    ("GET", "/insec_des_lab"),
    ("GET", "/xxe"),
    ("GET", "/xxe_lab"),
    ("GET", "/auth"),
    ("GET", "/auth_lab"),
    ("GET", "/auth_lab/signup"),
    ("GET", "/auth_lab/login"),
    ("GET", "/ba"),
    ("GET", "/ba_lab"),
    ("GET", "/data_exp"),
    ("GET", "/data_exp_lab"),
    ("GET", "/admin/"),
    ("GET", "/accounts/login/"),
    ("GET", "/accounts/signup/"),
    ("GET", "/login/"),
    ("GET", "/logout/"),
]


def smoke() -> list[tuple[str, int]]:
    out = []
    for method, path in ROUTES:
        try:
            r = CLIENT.get(path) if method == "GET" else CLIENT.post(path)
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
