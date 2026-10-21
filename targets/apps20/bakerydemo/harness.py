from __future__ import annotations
import json
import os
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4] / "external" / "bakerydemo"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bakerydemo.settings.dev")
_DB = Path(os.environ.get("SF_DB", REPO / f".sf_db_{os.getpid()}.sqlite3"))
os.environ["DATABASE_NAME"] = str(_DB)
os.environ["DJANGO_DEBUG"] = "1"

sys.path.insert(0, str(REPO))
os.chdir(REPO)          

import django  

django.setup()

from django.core.management import call_command  

call_command("migrate", verbosity=0, interactive=False, run_syncdb=True)


from django.contrib.auth import get_user_model  
from wagtail.models import Page  
_USER, _PASS = "admin", "passw0rd!"
User = get_user_model()
if not User.objects.filter(username=_USER).exists():
    User.objects.create_superuser(_USER, "admin@example.org", _PASS)

from bakerydemo.base.models import StandardPage  

home = Page.objects.filter(depth=2).first()          
_idx = _page = None
if home is not None:
    try:
        idx = StandardPage(title="Probe", slug="probe",
                           introduction="probe intro")
        home.add_child(instance=idx)
        page = StandardPage(title="Deep Page", slug="deep",
                            introduction="deep page intro")
        idx.add_child(instance=page)
        _idx, _page = idx, page
    except Exception:
        pass

CLIENT = None
from django.test import Client  

CLIENT = Client()
CLIENT.login(username=_USER, password=_PASS)


ROUTES: list[tuple[str, str, str]] = [
    ("GET", "/", "public"),                          
    ("GET", "/search/?q=bread", "public"),
    ("GET", "/sitemap.xml", "public"),
    ("GET", "/api/v2/pages/", "public"),
    ("GET", "/api/v2/pages/?type=bakerydemo.base.StandardPage", "public"),
    ("GET", "/admin/login/", "public"),
    ("GET", "/admin/", "session"),                   
    ("GET", "/admin/pages/", "session"),
    ("GET", "/admin/users/", "session"),
    ("GET", "/admin/documents/", "session"),
    ("GET", "/admin/images/", "session"),
    ("GET", "/admin/snippets/", "session"),
    ("GET", "/admin/forms/", "session"),
    ("GET", "/django-admin/", "session"),
    ("GET", "/documents/", "public"),
    ("GET", "/404/", "public"),
]
if _idx is not None:
    ROUTES += [
        ("GET", "/probe/", "page-tree"),             
        ("GET", "/probe/deep/", "page-tree"),
        ("GET", f"/api/v2/pages/{_page.id}/", "public"),
        ("GET", "/admin/pages/%d/edit/" % _page.id, "session"),
    ]


def smoke() -> list[tuple[str, int]]:
    
    out = []
    for method, path, auth in ROUTES:
        try:
            if method == "GET":
                r = CLIENT.get(path)
            else:
                r = CLIENT.post(path, data=json.dumps({}),
                                content_type="application/json")
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
