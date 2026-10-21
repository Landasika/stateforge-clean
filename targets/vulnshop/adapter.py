from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import app as vshop


@dataclass
class TargetSpec:
    module: str                 
    init: Callable              
    db_path: Path | None        
    make_server: Callable       
    healthy_path: str           
    observes: dict = field(default_factory=dict)  
def _make_server(app, host: str, port: int):
    from werkzeug.serving import make_server

    return make_server(host, port, app, threaded=False)


def _init(db_path: str = None) -> str:
    path = db_path or vshop.DB_PATH
    vshop.init_database(path)
    return path


SPEC = TargetSpec(
    module="stateforge.targets.vulnshop.app",
    init=_init,
    db_path=Path(vshop.DB_PATH),
    make_server=_make_server,
    healthy_path="/",
    observes={
        "GET /orders/<int:oid>": ["status", "total", "paid_amount"],
        "GET /coupons/<code>": ["used", "discount"],
        "GET /auth/me": ["id", "username", "role"],
    },
)
