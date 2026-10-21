from __future__ import annotations
from typing import Any, Callable
from stateforge.adapters.generic_web import GenericWebAdapter
def wsgi_adapter(app: Callable, auth_headers: dict | None = None,
                 base_url: str = "") -> GenericWebAdapter:
    
    from werkzeug.test import Client

    client: Any = Client(app)
    adapter = GenericWebAdapter.__new__(GenericWebAdapter)
    adapter.client = client          
    adapter.auth_headers = auth_headers or {}
    adapter.base_url = base_url
    return adapter
