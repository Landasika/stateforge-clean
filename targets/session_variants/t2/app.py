from __future__ import annotations
from flask import Flask, current_app, request, session
DEFAULT_PASSCODE = "gate-t2"


def target_a() -> None:
    current_app.config.setdefault("T2_HITS", []).append("a")


def target_b() -> None:
    current_app.config.setdefault("T2_HITS", []).append("b")


def save_state(value) -> None:
    
    session["token"] = value


def save_dynamic(state, value) -> None:
    
    session[state["key"]] = value


def create_app(passcode: str = DEFAULT_PASSCODE) -> Flask:
    app = Flask(__name__)
    app.secret_key = "stateforge-t2-dev-only"
    app.config["PASSCODE"] = passcode

    @app.post("/login")
    def login():
        if request.form.get("code") != current_app.config["PASSCODE"]:
            return "deny", 403
        save_state(7)
        return "ok"

    @app.post("/dynamic")
    def dynamic_write():
        save_dynamic({"key": "token"}, 7)
        return "ok"

    @app.get("/a")
    def vault_a():
        token = session.get("token")
        if token is None:
            return "deny", 401
        target_a()
        return "A"

    @app.get("/b")
    def vault_b():
        token = session.get("token")
        if token:
            target_b()
            return "B"
        return "deny", 401

    return app
