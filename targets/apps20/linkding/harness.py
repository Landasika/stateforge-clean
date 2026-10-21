from __future__ import annotations
import datetime
import os
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4] / "external" / "linkding"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bookmarks.settings")
os.environ.setdefault("LD_DISABLE_BACKGROUND_TASKS", "True")  
_DB = Path(os.environ.get("SF_DB", REPO / f".sf_db_{os.getpid()}.sqlite3"))
os.makedirs(REPO / "data", exist_ok=True)  
sys.path.insert(0, str(REPO))
import django  

django.setup()

from django.conf import settings  

settings.DATABASES["default"]["NAME"] = str(_DB)
settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver", "localhost"]

from django.core.management import call_command  

call_command("migrate", verbosity=0, interactive=False, run_syncdb=True)

from django.contrib.auth import get_user_model  

_USER, _PASS = "probe", "Passw0rd!"
User = get_user_model()
if not User.objects.filter(username=_USER).exists():
    User.objects.create_superuser(_USER, "probe@linkding.local", _PASS)

from bookmarks.models import (  
    ApiToken,
    Bookmark,
    BookmarkBundle,
    FeedToken,
    Tag,
)

_NOW = datetime.datetime.now(datetime.timezone.utc)
_owner = User.objects.get(username=_USER)
_tag = Tag.objects.filter(owner=_owner, name="probe-tag").first()
if _tag is None:
    _tag = Tag.objects.create(name="probe-tag", owner=_owner, date_added=_NOW)
_bm = Bookmark.objects.filter(owner=_owner, url="https://example.com/probe").first()
if _bm is None:
    _bm = Bookmark(
        url="https://example.com/probe",
        title="Probe Bookmark",
        description="probe",
        unread=True,
        shared=True,
        date_added=_NOW,
        date_modified=_NOW,
        owner=_owner,
    )
    _bm.save()
    _bm.tags.add(_tag)
_bm_archived = Bookmark.objects.filter(owner=_owner, url="https://example.com/archived").first()
if _bm_archived is None:
    _bm_archived = Bookmark(
        url="https://example.com/archived",
        title="Archived Probe",
        is_archived=True,
        date_added=_NOW,
        date_modified=_NOW,
        owner=_owner,
    )
    _bm_archived.save()
_bundle = BookmarkBundle.objects.filter(owner=_owner, name="Probe Bundle").first()
if _bundle is None:
    _bundle = BookmarkBundle.objects.create(name="Probe Bundle", owner=_owner)
_feed = FeedToken.objects.filter(user=_owner).first()
if _feed is None:
    _feed = FeedToken.objects.create(user=_owner)
_api_token = ApiToken.objects.filter(user=_owner, name="probe-token").first()
if _api_token is None:
    _api_token = ApiToken.objects.create(user=_owner, name="probe-token")

from django.test import Client  

CLIENT = Client()
CLIENT.login(username=_USER, password=_PASS)

BM_ID = _bm.pk
TAG_ID = _tag.pk
BUNDLE_ID = _bundle.pk
FEED_KEY = _feed.key
API_TOKEN = _api_token.key


ROUTES: list[tuple[str, str, str]] = [
    ("GET", "/", "public"),                      
    ("GET", "/login/", "public"),
    
    ("GET", "/bookmarks", "session"),
    ("GET", "/bookmarks/archived", "session"),
    ("GET", "/bookmarks/shared", "session"),
    ("GET", "/bookmarks/new", "session"),
    ("GET", f"/bookmarks/{BM_ID}/edit", "session+db"),  
    ("GET", "/tags", "session"),
    ("GET", "/tags/new", "session"),
    ("GET", f"/tags/{TAG_ID}/edit", "session+db"),     
    ("GET", "/tags/merge", "session"),
    ("GET", "/bundles", "session"),
    ("GET", "/bundles/new", "session"),
    ("GET", f"/bundles/{BUNDLE_ID}/edit", "session+db"),
    ("GET", "/bundles/preview", "session"),
    ("GET", "/settings", "session"),
    ("GET", "/settings/general", "session"),
    ("GET", "/settings/integrations", "session"),
    ("GET", "/settings/import", "session"),
    ("GET", "/settings/export", "session"),
    ("GET", "/admin/tasks/", "session"),
    ("GET", "/admin/", "session"),
    
    ("GET", f"/feeds/{FEED_KEY}/all", "capability"),
    ("GET", f"/feeds/{FEED_KEY}/unread", "capability"),
    ("GET", f"/feeds/{FEED_KEY}/shared", "capability"),
    ("GET", "/feeds/shared", "public"),
    ("GET", "/api/", "api-token"),
    ("GET", "/api/bookmarks/", "api-token"),
    ("GET", "/api/bookmarks/archived/", "api-token"),
    ("GET", f"/api/bookmarks/{BM_ID}/", "api-token+db"),
    ("GET", "/api/tags/", "api-token"),
    ("GET", "/api/tags/?limit=5", "api-token"),
    ("GET", "/api/bundles/", "api-token"),
    ("GET", "/api/user/profile/", "api-token"),
    
    ("GET", "/health", "public"),
    ("GET", "/manifest.json", "public"),
    ("GET", "/custom_css", "public"),
    ("GET", "/opensearch.xml", "public"),
    ("GET", "/assets/1", "session+db"),           
]


def smoke() -> list[tuple[str, int]]:
    
    out = []
    for method, path, auth in ROUTES:
        try:
            headers = {}
            if auth.startswith("api-token"):
                headers["Authorization"] = f"Token {API_TOKEN}"
            extra = {f"HTTP_{k.replace('-', '_').upper()}": v
                     for k, v in headers.items()}
            r = CLIENT.get(path, **extra) if method == "GET" else CLIENT.post(path, **extra)
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
