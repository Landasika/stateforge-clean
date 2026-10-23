from __future__ import annotations

import os
import sys
from pathlib import Path

TARGET_ROOT = Path(__file__).resolve().parent
REPO = TARGET_ROOT / "src"

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pygoat.settings")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.chdir(REPO)

import django

django.setup()

from django.conf import settings

_DB = Path(os.environ.get("SF_DB", TARGET_ROOT / f".sf_db_{os.getpid()}.sqlite3"))
settings.DATABASES["default"]["NAME"] = str(_DB)

from django.core.management import call_command

call_command("migrate", verbosity=0, interactive=False, run_syncdb=True)

_USER = "probe"
_PASS = "Passw0rd!"
from django.contrib.auth import get_user_model

User = get_user_model()
if not User.objects.filter(username=_USER).exists():
    User.objects.create_superuser(_USER, "probe@pygoat.local", _PASS)

from django.test import Client

CLIENT = Client()
CLIENT.login(username=_USER, password=_PASS)

ROUTES = [
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


def smoke():
    results = []
    for method, path in ROUTES:
        try:
            response = (CLIENT.get(path) if method == "GET"
                        else CLIENT.post(path))
            results.append((f"{method} {path}", response.status_code))
        except Exception as exc:
            results.append((f"{method} {path}",
                            f"EXC:{type(exc).__name__}:{exc}"))
    return results


if __name__ == "__main__":
    results = smoke()
    ok = sum(1 for _, status in results
             if isinstance(status, int) and status < 500)
    print(f"smoke: {ok}/{len(results)} non-5xx")
    for route, status in results:
        print(f"  {status!s:>4}  {route}")
