from __future__ import annotations
import os
import shutil
import sys
import tempfile
from pathlib import Path
REPO = Path(__file__).resolve().parents[4] / "external" / "mezzanine"
_SITE = Path(tempfile.mkdtemp(prefix=f"mezz_site_{os.getpid()}_"))
shutil.copytree(REPO / "mezzanine" / "project_template" / "project_name",
                _SITE / "project_name")

_HOST_URLS = '''\
from django.contrib import admin
from django.urls import include, path

from mezzanine.pages import views as pages_views

admin.autodiscover()

urlpatterns = [
    path("admin/", include(admin.site.urls)),
    # 首页用页树里的 "/" 页(官方模板注释里的第二种接法),模板 index.html 不存在
    path("", pages_views.page, {"slug": "/"}, name="home"),
    path("", include("mezzanine.urls")),
]
'''

_HOST_SETTINGS = '''\
from .settings import *  # noqa: F401,F403

SECRET_KEY = "sf-mezzanine-harness-key"
ALLOWED_HOSTS = ["*"]
DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "",  # harness 导入后按 SF_DB 覆写
    }
}

# 官方模板默认注释掉的 accounts 应用:提供 /accounts/* 会话门路由
INSTALLED_APPS = list(INSTALLED_APPS) + ["mezzanine.accounts"]
ACCOUNTS_PROFILE_VIEWS_ENABLED = True
'''

(_SITE / "project_name" / "urls.py").write_text(_HOST_URLS)
(_SITE / "project_name" / "sf_settings.py").write_text(_HOST_SETTINGS)

os.environ["DJANGO_SETTINGS_MODULE"] = "project_name.sf_settings"
sys.path.insert(0, str(_SITE))

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
    User.objects.create_superuser(_USER, "probe@mezzanine.local", _PASS)


from django.contrib.contenttypes.models import ContentType  
from django.utils import timezone  
from mezzanine.blog.models import BlogCategory, BlogPost  
from mezzanine.galleries.models import Gallery  
from mezzanine.generic.models import AssignedKeyword, Keyword  
from mezzanine.pages.models import RichTextPage  

_user = User.objects.get(username=_USER)
_now = timezone.now()
RichTextPage.objects.get_or_create(
    slug="/", defaults=dict(title="Home", content="sf harness home"))
RichTextPage.objects.get_or_create(
    slug="about", defaults=dict(title="About", content="sf about page"))
_cat, _ = BlogCategory.objects.get_or_create(title="sfcat")
_post1, _ = BlogPost.objects.get_or_create(
    slug="first-post",
    defaults=dict(title="First post", content="hello world", user=_user,
                  publish_date=_now, status=2))          
_post1.categories.add(_cat)
_kw, _ = Keyword.objects.get_or_create(title="sftag")
AssignedKeyword.objects.get_or_create(
    keyword=_kw, object_pk=str(_post1.id),
    content_type=ContentType.objects.get_for_model(_post1))
BlogPost.objects.get_or_create(
    slug="second-post",
    defaults=dict(title="Second post", content="second body", user=_user,
                  publish_date=_now, status=2))
Gallery.objects.get_or_create(slug="gallery", defaults=dict(title="My Gallery"))

from django.test import Client  

CLIENT = Client()
CLIENT.login(username=_USER, password=_PASS)

_YEAR = _post1.publish_date.year



ROUTES: list[tuple[str, str] | tuple[str, str, dict]] = [
    
    ("GET", "/"),
    ("GET", "/about/"),
    ("GET", "/nonexistent-page/"),
    
    ("GET", "/blog/"),
    ("GET", "/blog/first-post/"),
    ("GET", "/blog/second-post/"),
    ("GET", f"/blog/archive/{_YEAR}/"),
    ("GET", "/blog/category/sfcat/"),
    ("GET", "/blog/tag/sftag/"),
    ("GET", "/blog/author/probe/"),
    ("GET", "/blog/feeds/rss/"),
    ("GET", "/gallery/"),
    ("GET", "/search/?q=post"),
    ("GET", "/sitemap.xml"),
    
    ("GET", "/comment/"),
    ("GET", "/rating/"),
    
    ("POST", "/edit/", {"app": "blog", "model": "blogpost", "id": _post1.id,
                        "fields": "content", "content": "hello world"}),
    ("GET", "/set_site/?site_id=1"),
    
    ("GET", "/accounts/"),
    ("GET", "/accounts/login/"),
    ("GET", "/accounts/signup/"),
    ("GET", "/users/"),
    ("GET", "/users/probe/"),
    
    ("GET", "/password_reset/"),
    ("GET", "/password_reset/done/"),
    
    ("GET", "/admin/"),
    ("GET", "/admin/blog/blogpost/"),
    ("GET", "/admin/pages/page/"),
    
    ("GET", "/accounts/logout/"),
]


def smoke() -> list[tuple[str, str | int]]:
    out = []
    for route in ROUTES:
        method, path = route[0], route[1]
        data = route[2] if len(route) > 2 else {}
        try:
            if method == "GET":
                r = CLIENT.get(path)
            else:
                r = CLIENT.post(path, data)
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
