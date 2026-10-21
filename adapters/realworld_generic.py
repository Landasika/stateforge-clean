from __future__ import annotations

from stateforge.adapters.generic_web import GenericWebAdapter


def realworld_generic() -> GenericWebAdapter:
    import sys
    from pathlib import Path
    REPO = Path(__file__).parents[3] / "external" / "realworld-django-ninja"
    sys.path.insert(0, str(REPO))
    import os
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    os.environ["DEBUG"] = "true"
    import django
    django.setup()

    from config.asgi import application  
    from django.test import Client
    client = Client()
    client.generic = lambda method, path, **kw: client.request(
        REQUEST_METHOD=method, PATH_INFO=path, **kw)

    adapter = GenericWebAdapter.__new__(GenericWebAdapter)
    adapter.client = client
    adapter.auth_headers = {}
    adapter.base_url = ""
    return adapter
