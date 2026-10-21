from __future__ import annotations
import importlib.util
import json
import os
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
_HERE = Path(__file__).resolve().parent
_APP_SPEC = importlib.util.spec_from_file_location(
    f"_sf_session_gate_app_{os.getpid()}_{uuid.uuid4().hex[:8]}",
    _HERE / "app.py")
_APP_MOD = importlib.util.module_from_spec(_APP_SPEC)
sys.modules[_APP_SPEC.name] = _APP_MOD
_APP_SPEC.loader.exec_module(_APP_MOD)
create_app = _APP_MOD.create_app
DEFAULT_PASSCODE = _APP_MOD.DEFAULT_PASSCODE
PASSCODE_CONFIG_KEY = _APP_MOD.PASSCODE_CONFIG_KEY
TARGET_HITS_KEY = _APP_MOD.TARGET_HITS_KEY
SESSION_ABSENT = _APP_MOD.SESSION_ABSENT
SESSION_DECODED = _APP_MOD.SESSION_DECODED
SESSION_INVALID = _APP_MOD.SESSION_INVALID
SESSION_UNKNOWN = _APP_MOD.SESSION_UNKNOWN
SessionSnapshot = _APP_MOD.SessionSnapshot

_APP = create_app()
_CLIENT = _APP.test_client()





def _replace_client():
    global _CLIENT
    _CLIENT = _APP.test_client()
    return _CLIENT


def reset_state() -> None:
    

    _replace_client()
    _APP.config.setdefault(TARGET_HITS_KEY, []).clear()


@contextmanager
def input_scope():
    

    reset_state()
    try:
        yield _CLIENT
    finally:
        _replace_client()


def current_client():
    return _CLIENT


def target_hits() -> list[dict]:
    return _APP_MOD.target_hits(_APP)

def observe_session(client=None) -> "SessionSnapshot":
    return _APP_MOD.observe_session(client or _CLIENT, _APP)
def session_view(client=None):
    
    from stateforge.state.session_observation import snapshot_view
    return snapshot_view(observe_session(client), client_id="client-0",
                         observation_point="after_response",
                         source="flask-signed-cookie",
                         observer_id="flask-signed-cookie-reader")

def sf_state_observer():
    from stateforge.state.session_observation import SessionRuntimeObserver
    return SessionRuntimeObserver(session_view)




def _coerce(value):
    
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return value


def _dispatch_request(step: dict, client=None):
    client = client or _CLIENT
    method = str(step.get("method", "GET")).upper()
    path = str(step.get("path", "/"))

    kwargs: dict = {}
    headers = step.get("header")
    if headers is None:
        headers = step.get("headers")
    if isinstance(headers, dict):
        kwargs["headers"] = {str(k): str(v) for k, v in headers.items()}

    form = step.get("form")
    if isinstance(form, dict):
        kwargs["data"] = {str(k): _coerce(v) for k, v in form.items()}

    json_body = step.get("json")
    if isinstance(json_body, dict):
        kwargs["json"] = {str(k): _coerce(v) for k, v in json_body.items()}

    query = step.get("query")
    if isinstance(query, dict):
        kwargs["query_string"] = {str(k): _coerce(v) for k, v in query.items()}
    
    return client.open(path, method=method, **kwargs)

def _handle(step) -> None:
    if isinstance(step, dict):
        _dispatch_request(step)


def _decode(data: bytes):
    try:
        return json.loads(data) if data else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def target(data: bytes) -> None:
    

    seed = _decode(data)
    if seed is None:
        return
    if isinstance(seed, dict) and isinstance(seed.get("steps"), list):
        for step in seed["steps"]:
            _handle(step)
        return
    _handle(seed)


def run_input(steps) -> None:
    
    with input_scope():
        for step in steps:
            _handle(step)
