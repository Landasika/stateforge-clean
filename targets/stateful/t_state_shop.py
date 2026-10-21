import json
_SESSION = {}      
session = _SESSION  
_DB = {"users": {}, "orders": {}}   
HITS = []          
def reset_state() -> None:
    _SESSION.clear()
    _DB["users"].clear()
    _DB["orders"].clear()
    HITS.clear()


def register_ok():
    return "registered"
def order_created():
    return "order"


def ship_privileged():
    return "shipped"


def ship_denied():
    return 403


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
    if op == "register":
        user = body.get("user", "")
        password = body.get("password", "")
        if isinstance(user, str) and user and isinstance(password, str) and password:
            _DB["users"][user] = {"password": password}
            session["uid"] = user               
            HITS.append("register_ok")
            register_ok()
    elif op == "create_order":
        uid = session.get("uid")
        if uid in _DB["users"]:                 
            oid = str(len(_DB["orders"]) + 1)
            _DB["orders"][oid] = {"owner": uid,
                                  "item": str(body.get("item", ""))}
            session["order_id"] = oid
            HITS.append("order_created")
            order_created()
    elif op == "ship_order":
        oid = body.get("order") or session.get("order_id")
        order = _DB["orders"].get(oid) if isinstance(oid, str) else None
        if order is None:
            HITS.append("ship_denied")          
            ship_denied()
        elif order["owner"] == session.get("uid"):
            HITS.append("ship_privileged")      
            ship_privileged()
        else:
            HITS.append("ship_denied")          
            ship_denied()
