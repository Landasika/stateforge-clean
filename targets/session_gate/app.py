from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Mapping
from flask import Flask, current_app, request, session
DEFAULT_PASSCODE = "valid"
PASSCODE_CONFIG_KEY = "SESSION_GATE_PASSCODE"
DEV_SECRET_KEY = "stateforge-session-gate-dev-only-not-for-production"
TARGET_HITS_KEY = "SESSION_GATE_TARGET_HITS"
SESSION_ABSENT = "absent"       
SESSION_DECODED = "decoded"     
SESSION_INVALID = "invalid"     
SESSION_UNKNOWN = "unknown"     


@dataclass(frozen=True)
class SessionSnapshot:
    
    status: str
    values: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None
    cookie_name: str = "session"
    @property
    def present(self) -> bool:
        return self.status != SESSION_ABSENT

    @property
    def verified(self) -> bool:
        return self.status == SESSION_DECODED
    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


def create_app(passcode: str = DEFAULT_PASSCODE,
               routes: Mapping[str, str] | None = None) -> Flask:
    app = Flask(__name__)
    app.secret_key = DEV_SECRET_KEY
    app.config[PASSCODE_CONFIG_KEY] = passcode
    app.config[TARGET_HITS_KEY] = []
    _register_routes(app, routes)
    return app





def observe_session(client, app: Flask | None = None) -> SessionSnapshot:
    

    app = app or client.application
    interface = app.session_interface
    cookie_name = interface.get_cookie_name(app)
    cookie = client.get_cookie(cookie_name)
    if cookie is None or not cookie.value:
        return SessionSnapshot(SESSION_ABSENT, cookie_name=cookie_name)

    serializer = interface.get_signing_serializer(app)
    if serializer is None:
        return SessionSnapshot(SESSION_UNKNOWN, cookie_name=cookie_name,
                               error="session interface has no serializer")
    try:
        payload = serializer.loads(cookie.value)
    except Exception as exc:                       
        return SessionSnapshot(SESSION_INVALID, cookie_name=cookie_name,
                               error=type(exc).__name__)
    if not isinstance(payload, dict):
        return SessionSnapshot(SESSION_INVALID, cookie_name=cookie_name,
                               error="session payload is not a mapping")
    return SessionSnapshot(SESSION_DECODED, values=dict(payload),
                           cookie_name=cookie_name)


def target_hits(app: Flask) -> list[dict]:
    return [dict(item) for item in app.config.get(TARGET_HITS_KEY, [])]


def _hit(block: str) -> None:
    current_app.config.setdefault(TARGET_HITS_KEY, []).append({"block": block})
def target_block() -> None:
    
    _hit("target_block")


def truthy_target_block() -> None:
    _hit("truthy_target_block")


def membership_target_block() -> None:
    _hit("membership_target_block")


def subscript_target_block() -> None:
    _hit("subscript_target_block")




def _register_routes(app: Flask, routes: Mapping[str, str] | None = None) -> None:

    @app.post((routes or {}).get("authenticate", "/authenticate"))
    def authenticate():
        
        
        if request.form.get("passcode") != current_app.config[PASSCODE_CONFIG_KEY]:
            return "deny", 403
        session["uid"] = 7
        return "ok"
    @app.get((routes or {}).get("protected", "/protected"))
    def protected():
        uid = session.get("uid")
        if uid is None:
            return "deny", 401
        target_block()
        return "TARGET_BLOCK"
    
    
    @app.get((routes or {}).get("protected_truthy", "/protected_truthy"))
    def protected_truthy():
        uid = session.get("uid")
        if uid:
            truthy_target_block()
            return "TRUTHY_TARGET"
        return "deny", 401

    @app.get((routes or {}).get("protected_membership", "/protected_membership"))
    def protected_membership():
        if "uid" in session:
            membership_target_block()
            return "MEMBERSHIP_TARGET"
        return "deny", 401

    @app.get((routes or {}).get("protected_subscript", "/protected_subscript"))
    def protected_subscript():
        try:
            uid = session["uid"]
        except KeyError:
            return "deny", 401
        subscript_target_block()
        return "SUBSCRIPT_TARGET"

    @app.post((routes or {}).get("logout", "/logout"))
    def logout():
        session.pop("uid", None)
        return "ok"

    @app.post((routes or {}).get("clear", "/clear"))
    def clear():
        session.clear()
        return "ok"

    @app.post((routes or {}).get("noise", "/noise"))
    def noise():
        
        session["other"] = 7
        return "ok"
