from __future__ import annotations
import atexit
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from stateforge.runtime.snapshot.l2_sqlite import L2Sqlite
_HERE = Path(__file__).resolve().parent

_APP_SPEC = importlib.util.spec_from_file_location(
    f"_vulnshop_app_{os.getpid()}", _HERE / "app.py")
_APP_MOD = importlib.util.module_from_spec(_APP_SPEC)
sys.modules[_APP_SPEC.name] = _APP_MOD
_APP_SPEC.loader.exec_module(_APP_MOD)
create_app = _APP_MOD.create_app


_DB = Path(tempfile.gettempdir()) / f"vulnshop_{os.getpid()}_{__name__}.db"


def _sweep_dead_pid_dbs() -> None:
    
    for cand in Path(tempfile.gettempdir()).glob("vulnshop_*_*.db"):
        owner = cand.name.split("_")[1]        
        if not owner.isdigit():
            continue
        try:
            os.kill(int(owner), 0)
        except ProcessLookupError:
            pass                               
        except OSError:
            continue                           
        else:
            continue                           
        try:
            cand.unlink()
        except OSError:
            pass                               


_sweep_dead_pid_dbs()
_DB_CLEANUP_REGISTERED: set[str] = set()

def _register_db_cleanup(path: Path) -> None:
    if str(path) in _DB_CLEANUP_REGISTERED:
        return
    _DB_CLEANUP_REGISTERED.add(str(path))

    def _cleanup() -> None:
        try:
            path.unlink()
        except OSError:
            pass                    
        shutil.rmtree(path.parent / f"sf_baseline_{path.name}",
                      ignore_errors=True)   

    atexit.register(_cleanup)


_register_db_cleanup(_DB)
_APP = create_app(db_path=str(_DB), init_db=True)
_L2 = L2Sqlite(_DB, tpl_root=_DB.parent / f"sf_baseline_{_DB.name}")
_L2.snapshot_template("baseline")
_BINDINGS: dict[str, object] = {}          
_SLOT = re.compile(r"\?([A-Za-z_][A-Za-z0-9_]*)")


def reset_bindings() -> None:
    
    _BINDINGS.clear()


def reset_state() -> None:
    
    reset_bindings()
    if not _L2.template_exists("baseline"):
        raise RuntimeError(
            f"vulnshop DB 基线模板丢失: {_L2.root}/baseline/db.tpl")
    _L2.restore("baseline")






SF_STATE_FILES = [str(_DB)]
SF_MEMORY_RESET = reset_bindings
def sf_state_observer():
    from stateforge.targets.vulnshop.state_evidence import VulnshopStateObserver
    return VulnshopStateObserver(_DB)

def _sub(value: str) -> str:
    
    return _SLOT.sub(
        lambda m: str(_BINDINGS.get(m.group(1), m.group(0))), value)


def _coerce(value):
    
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return value
def _dispatch_request(app, bindings: dict, step: dict):
    def sub(v: str) -> str:
        return _SLOT.sub(
            lambda m: str(bindings.get(m.group(1), m.group(0))), v)
    method = str(step.get("method", "GET")).upper()
    path = sub(str(step.get("path", "/")))
    kwargs: dict = {"method": method,
                    "headers": {str(k): sub(str(v))
                                for k, v in (step.get("header") or {}).items()}}
    json_body = step.get("json")
    if isinstance(json_body, dict):
        kwargs["json"] = {k: _coerce(v) for k, v in json_body.items()}
    query = step.get("query")
    if isinstance(query, dict):
        kwargs["query_string"] = {k: _coerce(v) for k, v in query.items()}
    with app.test_request_context(path, **kwargs):
        resp = app.full_dispatch_request()
    extract = step.get("extract") or {}
    if extract and resp.status_code < 400:
        payload = resp.get_json(silent=True)
        if isinstance(payload, dict):
            for key, slot in extract.items():
                val = payload.get(key)
                if val is not None:
                    bindings[str(slot).lstrip("?")] = val
    return resp


def _request(step: dict):
    return _dispatch_request(_APP, _BINDINGS, step)


_LEGACY = None                                


def _legacy(data: bytes) -> None:
    global _LEGACY
    if _LEGACY is None:
        from stateforge.adapters.flask import FlaskAdapter
        _LEGACY = FlaskAdapter(_APP, headers={})
    try:
        _LEGACY.execute(data)
    except Exception:                          
        pass


def target(data: bytes) -> None:
    try:
        seed = json.loads(data) if data else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _legacy(data)                   
    if isinstance(seed, dict) and isinstance(seed.get("steps"), list):
        try:                                    
            for step in seed["steps"]:          
                if isinstance(step, dict):
                    _request(step)
        except Exception:                       
            pass
        return
    if isinstance(seed, dict) and isinstance(seed.get("path"), str):
        try:
            _request(seed)                     
        except Exception:                      
            pass
        return
    _legacy(data)







class VulnshopInstance:
    

    def __init__(self, db_path, guards: int):
        from stateforge.runtime.snapshot.l2_sqlite import L2Sqlite
        self.db_path = Path(db_path)
        self.guards = guards
        self.app = create_app(db_path=str(self.db_path), guards=guards,
                              init_db=True)
        self.bindings: dict[str, object] = {}
        self._l2 = L2Sqlite(self.db_path,
                            tpl_root=self.db_path.parent
                            / f"sf_baseline_{self.db_path.name}")
        self._l2.snapshot_template("baseline")
    def request(self, step: dict):
        return _dispatch_request(self.app, self.bindings, step)

    def reset(self) -> None:
        
        self.bindings.clear()
        if not self._l2.template_exists("baseline"):
            raise RuntimeError(
                f"实例 DB 基线模板丢失: {self._l2.root}/baseline/db.tpl")
        self._l2.restore("baseline")

    def observer(self):
        from stateforge.targets.vulnshop.state_evidence import \
            VulnshopStateObserver
        return VulnshopStateObserver(self.db_path)
    def auth_probe(self):
        from stateforge.targets.vulnshop.state_evidence import \
            observe_request_auth
        return observe_request_auth(self.bindings.get("token"),
                                    app_module=_APP_MOD,
                                    db_path=self.db_path)
def make_instance(db_path, guards: int) -> VulnshopInstance:
    return VulnshopInstance(db_path=db_path, guards=guards)
