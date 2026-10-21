from __future__ import annotations
import json
from typing import Any, Protocol


class _TestClient(Protocol):
    def get(self, path, **kw): ...
    def post(self, path, **kw): ...
    def request(self, method, path, **kw): ...


class GenericWebAdapter:
    

    def __init__(self, app: Any, auth_headers: dict | None = None,
                 base_url: str = ""):
        self.client: _TestClient = app.test_client()
        self.auth_headers = auth_headers or {}
        self.base_url = base_url

    def prepare(self, atheris) -> None:
        from stateforge.fuzzing.instrumentation import Instrumenter
        instrumenter = Instrumenter()
        
        for name in dir(self.client):
            obj = getattr(self.client, name, None)
            if callable(obj) and hasattr(obj, "__code__"):
                instrumenter.instrument_callable(obj, atheris)

    def execute(self, data: bytes) -> object:
        
        try:
            seed = json.loads(data) if data else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            seed = {}
        if not isinstance(seed, dict):
            seed = {}

        method = str(seed.get("method", "GET")).upper()
        path = self.base_url + str(seed.get("path", "/"))
        body = seed.get("body")
        headers = {**self.auth_headers, **(seed.get("headers") or {})}

        try:
            return self._request(method, path, body, headers)
        except Exception:                    
            return None

    def _request(self, method, path, body, headers):
        is_flask = hasattr(self.client, "open")
        if is_flask:
            if method == "GET":
                return self.client.get(path, headers=headers)
            if body is not None:
                return self.client.request(method, path, json=body,
                                            headers=headers)
            return self.client.request(method, path, headers=headers)
        else:
            
            extra = {f"HTTP_{k.replace('-', '_').upper()}": v
                     for k, v in headers.items()}
            if method == "GET":
                return self.client.get(path, **extra)
            data = json.dumps(body) if body is not None else None
            ct = "application/json" if body is not None else None
            return self.client.generic(method, path, data=data,
                                        content_type=ct, **extra)


def _client_sig(client) -> set:
    
    import inspect
    try:
        return set(inspect.signature(client.get).parameters.keys())
    except (ValueError, TypeError):
        return set()
