from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
REPO = Path(__file__).resolve().parents[4] / "external" / "django-blog-zinnia"
_SITE = Path(tempfile.mkdtemp(prefix=f"zinn_site_{os.getpid()}_"))
_HOST_SETTINGS = '''\
"""Sf host settings for django-blog-zinnia (modeled on demo/settings.py)."""
SECRET_KEY = "sf-zinnia-harness-key"
DEBUG = False
ALLOWED_HOSTS = ["*"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3",
                         "NAME": ""}}  # harness 导入后按 SF_DB 覆写
TIME_ZONE = "UTC"
USE_TZ = True
USE_I18N = True
SITE_ID = 1
LANGUAGE_CODE = "en"
STATIC_URL = "/static/"
MEDIA_URL = "/media/"
ROOT_URLCONF = "sf_zinnia_urls"
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "zinnia.context_processors.version",
            ]
        },
    }
]
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.sitemaps",
    "django.contrib.admin",
    "django.contrib.staticfiles",
    "django_comments",
    "mptt",
    "tagging",
    "zinnia",
]
ZINNIA_PAGINATION = 3
'''

_HOST_URLS = '''\
from django.conf.urls import include, url
from django.contrib import admin
from django.contrib.sitemaps.views import index, sitemap

from zinnia.sitemaps import AuthorSitemap, CategorySitemap, EntrySitemap, TagSitemap

sitemaps = {"tags": TagSitemap, "blog": EntrySitemap,
            "authors": AuthorSitemap, "categories": CategorySitemap}

urlpatterns = [
    url(r"^blog/", include("zinnia.urls", namespace="zinnia")),
    url(r"^comments/", include("django_comments.urls")),
    url(r"^admin/", admin.site.urls),
    url(r"^sitemap\\.xml$", index, {"sitemaps": sitemaps}),
    url(r"^sitemap-(?P<section>.+)\\.xml$", sitemap, {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap"),
]
'''

(_SITE / "sf_zinnia_settings.py").write_text(_HOST_SETTINGS)
(_SITE / "sf_zinnia_urls.py").write_text(_HOST_URLS)

os.environ["DJANGO_SETTINGS_MODULE"] = "sf_zinnia_settings"
sys.path.insert(0, str(_SITE))
sys.path.insert(0, str(REPO))

import django  

django.setup()

from django.conf import settings  

_DB = Path(os.environ.get("SF_DB", _SITE / f".sf_db_{os.getpid()}.sqlite3"))
settings.DATABASES["default"]["NAME"] = str(_DB)

from django.core.management import call_command  


call_command("migrate", verbosity=0, interactive=False, run_syncdb=True)

_USER, _PASS = "probe", "Passw0rd!"
from django.contrib.auth import get_user_model  

User = get_user_model()
if not User.objects.filter(username=_USER).exists():
    User.objects.create_superuser(_USER, "probe@zinnia.local", _PASS)


from django.contrib.sites.models import Site  

from zinnia.managers import PUBLISHED  
from zinnia.models import Author, Category, Entry  
_site = Site.objects.get(pk=settings.SITE_ID)
_author = Author.objects.get(username=_USER)
_cat, _ = Category.objects.get_or_create(title="sfcat", slug="sfcat")
_e1, _ = Entry.objects.get_or_create(
    slug="first-entry",
    defaults=dict(title="First entry", content="hello sf world",
                  status=PUBLISHED))
_e1.authors.add(_author)
_e1.categories.add(_cat)
_e1.sites.add(_site)
_e1.tags = '"sftag" "sfcase"'
_e1.save()
_e2, _ = Entry.objects.get_or_create(
    slug="second-entry",
    defaults=dict(title="Second entry", content="second body",
                  status=PUBLISHED))
_e2.authors.add(_author)
_e2.sites.add(_site)
_e2.save()
from django.test import Client  

CLIENT = Client()
CLIENT.login(username=_USER, password=_PASS)

_d = _e1.publication_date
_Y, _M, _Dy = _d.year, f"{_d.month:02d}", f"{_d.day:02d}"

from zinnia.url_shortener import get_url_shortener  

_SHORT = urlsplit(get_url_shortener()(_e1)).path

ROUTES: list[tuple[str, str]] = [
    
    ("GET", "/blog/"),
    ("GET", "/blog/page/1/"),
    ("GET", f"/blog/{_Y}/"),
    ("GET", f"/blog/{_Y}/{_M}/"),
    ("GET", f"/blog/{_Y}/{_M}/{_Dy}/"),
    ("GET", f"/blog/{_Y}/week/42/"),
    ("GET", "/blog/today/"),
    
    ("GET", f"/blog/{_Y}/{_M}/{_Dy}/first-entry/"),
    ("GET", _SHORT),
    
    ("GET", "/blog/authors/"),
    ("GET", "/blog/authors/probe/"),
    ("GET", "/blog/categories/"),
    ("GET", "/blog/categories/sfcat/"),
    ("GET", "/blog/tags/"),
    ("GET", "/blog/tags/sftag/"),
    
    ("GET", "/blog/search/?pattern=first"),
    ("GET", "/blog/random/"),
    ("GET", "/blog/sitemap/"),
    ("GET", "/blog/feeds/"),
    ("GET", "/blog/feeds/discussions/"),
    ("GET", "/blog/feeds/tags/sftag/"),
    ("GET", "/blog/feeds/authors/probe/"),
    ("GET", "/blog/feeds/categories/sfcat/"),
    ("GET", f"/blog/feeds/comments/{_Y}/{_M}/{_Dy}/first-entry/"),
    
    ("GET", "/blog/humans.txt"),
    ("GET", "/blog/rsd.xml"),
    ("GET", "/blog/opensearch.xml"),
    ("GET", "/blog/wlwmanifest.xml"),
    
    ("GET", "/blog/trackback/1/"),
    ("GET", "/blog/quick-entry/"),
    ("GET", "/blog/comments/success/"),
    
    ("GET", "/sitemap.xml"),
    ("GET", "/sitemap-blog.xml"),
    ("GET", "/admin/"),
    ("GET", "/admin/zinnia/entry/"),
    ("GET", "/admin/login/"),
    ("GET", "/comments/post/"),
    ("GET", "/blog/nonexistent/"),
]


def smoke() -> list[tuple[str, str | int]]:
    out = []
    for method, path in ROUTES:
        try:
            r = CLIENT.get(path) if method == "GET" else CLIENT.post(path)
            out.append((f"{method} {path}", r.status_code))
        except Exception as exc:                 
            out.append((f"{method} {path}", f"EXC:{type(exc).__name__}:{exc}"[:160]))
    return out


if __name__ == "__main__":
    results = smoke()
    ok = sum(1 for _, s in results if isinstance(s, int) and s < 500)
    print(f"smoke: {ok}/{len(results)} non-5xx site={_SITE}")
    for route, status in results:
        print(f"  {status!s:>4}  {route}")
