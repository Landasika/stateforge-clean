import json
_SESSION = {}      
session = _SESSION  
HITS = []          
def reset_state() -> None:
    _SESSION.clear()
    HITS.clear()
def login_ok():
    return "login"


def deep_state_profile():
    return "stateful-profile"

def profile_anon():
    return "anon-profile"


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
        user = body.get("user", "")
        if isinstance(user, str) and user:
            session["uid"] = user               
            HITS.append("login_ok")
            login_ok()
    elif op == "profile":
        uid = session.get("uid")
        if uid:                                 
            HITS.append("deep_state_profile")
            deep_state_profile()
        else:
            HITS.append("profile_anon")
            profile_anon()
