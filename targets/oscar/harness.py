from __future__ import annotations

import os
import sys
from pathlib import Path

TARGET_ROOT = Path(__file__).resolve().parent
SRC = TARGET_ROOT / "src"
SANDBOX = TARGET_ROOT / "sandbox"

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sandbox.settings")
for path in (str(SRC), str(SANDBOX.parent), str(SANDBOX)):
    if path not in sys.path:
        sys.path.insert(0, path)
os.chdir(SANDBOX)

_DB = Path(os.environ.get("SF_DB", TARGET_ROOT / f".sf_db_{os.getpid()}.sqlite"))
os.environ["DATABASE_NAME"] = str(_DB)

import django

django.setup()

from django.conf import settings

settings.DATABASES["default"]["NAME"] = str(_DB)
settings.ALLOWED_HOSTS = ["*"]

from django.core.management import call_command

try:
    call_command("migrate", verbosity=0, interactive=False, run_syncdb=True)
except Exception:
    import django.db

    try:
        call_command("migrate", "catalogue", "0017_auto_20190816_0938",
                     verbosity=0, interactive=False, fake=True)
        call_command("migrate", verbosity=0, interactive=False, run_syncdb=True)
    except django.db.Error as exc:
        print(f"[oscar] migrate fallback note: {exc}", file=sys.stderr)

_USER = "probe"
_PASS = "Passw0rd!"
from django.contrib.auth import get_user_model

User = get_user_model()
if not User.objects.filter(username=_USER).exists():
    User.objects.create_superuser(_USER, "probe@oscar.local", _PASS)

from django.test import Client

CLIENT = Client()
CLIENT.login(username=_USER, password=_PASS)

ROUTES = [
    ("GET", "/"),
    ("GET", "/catalogue/"),
    ("GET", "/search/"),
    ("GET", "/basket/"),
    ("GET", "/accounts/"),
    ("GET", "/accounts/login/"),
    ("GET", "/accounts/register/"),
    ("GET", "/accounts/password-reset/"),
    ("GET", "/checkout/"),
    ("GET", "/shipping-address/"),
    ("GET", "/payment/"),
    ("GET", "/order-placement/"),
    ("GET", "/orders/"),
    ("GET", "/offers/"),
    ("GET", "/coupons/"),
    ("GET", "/dashboard/"),
    ("GET", "/dashboard/catalogue/"),
    ("GET", "/dashboard/orders/"),
    ("GET", "/dashboard/users/"),
    ("GET", "/dashboard/partners/"),
    ("GET", "/dashboard/reports/"),
    ("GET", "/dashboard/comms/"),
    ("GET", "/dashboard/reviews/"),
    ("GET", "/admin/"),
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
