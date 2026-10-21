import json
_SESSION = {}      
session = _SESSION  
HITS = []          
def reset_state() -> None:
    _SESSION.clear()
    HITS.clear()
def login_ok():
    return "login"


def gate_granted():
    return "admin-panel"

def unauthorized():
    return 401


def target(data: bytes) -> None:
    try:
        seed = json.loads(data) if data else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return                                  
    if isinstance(seed, dict) and isinstance(seed.get("steps"), list):
        for step in seed["steps"]:              
            _handle(step)
        return
    _handle(seed)


def _handle(seed) -> None:
    if not isinstance(seed, dict):
        return                                  
    body = seed.get("json", seed)
    if not isinstance(body, dict):
        return                                  
    op = str(body.get("op", ""))
    if op == "login":
        role = body.get("role", "")
        if isinstance(role, str) and role:
            session["role"] = role              
            HITS.append("login_ok")
            login_ok()
    elif op == "admin_panel":
        role = session.get("role")
        if role == "admin":                     
            HITS.append("gate_granted")
            gate_granted()
        else:
            HITS.append("unauthorized")
            unauthorized()
