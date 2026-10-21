from __future__ import annotations
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from stateforge.targets.vulnshop.adapter import TargetSpec

VAMPI_DIR = Path(__file__).parent


def make_app(vulnerable: int = 1, token_ttl: int = 600):
    
    os.environ["vulnerable"] = str(vulnerable)
    os.environ["tokentimetolive"] = str(token_ttl)
    if str(VAMPI_DIR) not in sys.path:
        sys.path.insert(0, str(VAMPI_DIR))
    import config  

    return config.vuln_app.app

def _make_server(flask_app, host: str, port: int):
    from werkzeug.serving import make_server
    return make_server(host, port, flask_app, threaded=False)
def _init() -> Path:
    
    if str(VAMPI_DIR) not in sys.path:
        sys.path.insert(0, str(VAMPI_DIR))
    from config import db
    from models.books_model import Book  
    from models.user_model import User

    db.drop_all()
    db.create_all()
    User.init_db_users()
    return VAMPI_DIR / "database" / "database.db"


def make_spec(vulnerable: int = 1) -> TargetSpec:
    return TargetSpec(
        module="app",  
        init=_init,
        db_path=VAMPI_DIR / "database" / "database.db",
        make_server=lambda flask_app, host, port: _make_server(flask_app, host, port),
        healthy_path="/",
        observes={
            "GET /users/v1/{username}": ["username", "email"],
            "GET /books/v1/{book_title}": ["secret"],
            "GET /me": ["data.username", "data.admin"],
        },
    )


SPEC = make_spec()
