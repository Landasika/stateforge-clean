from __future__ import annotations
import sqlite3
from pathlib import Path
from stateforge.state.runtime_observer import (
    Evidence,
    NOT_OBSERVABLE,
    OBSERVABLE,
    SCOPE_RESOURCE,
    SCOPE_USER,
    StateKey,
    StateObservation,
    VALUE_KIND_BOOLEAN,
    VALUE_KIND_ENUM,
    VALUE_KIND_NUMBER,
)
class VulnshopStateObserver:
    name = "vulnshop-db"
    subject_families = {
        "User.exists": OBSERVABLE,
        "User.id": OBSERVABLE,
        "User.role": OBSERVABLE,
        "Order.exists": OBSERVABLE,
        "Order.status": OBSERVABLE,
        "Order.user_id": OBSERVABLE,
        "Coupon.used": OBSERVABLE,
        "Session.*": NOT_OBSERVABLE,
    }
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
    def _rows(self, sql: str) -> list[tuple]:
        
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def _verified(self, predicate: str, entity: str, scope: str,
                  value: bool, table: str, *, subject: str | None = None,
                  observed_value: object = None,
                  value_kind: str | None = None) -> StateObservation:
        return StateObservation(
            key=StateKey(predicate, entity, scope), value=value,
            evidence=Evidence.RUNTIME_VERIFIED, source=f"db:{table}",
            subject=subject, observed_value=observed_value,
            value_kind=value_kind)

    def observe(self) -> list[StateObservation]:
        out: list[StateObservation] = []
        for username, uid, role in self._rows(
                "SELECT username, id, role FROM users"):
            out.append(self._verified("User.exists", str(username),
                                      SCOPE_USER, True, "users",
                                      subject="User.exists",
                                      value_kind=VALUE_KIND_BOOLEAN))
            out.append(self._verified(f"User.id={uid}", str(username),
                                      SCOPE_USER, True, "users",
                                      subject="User.id",
                                      observed_value=uid,
                                      value_kind=VALUE_KIND_NUMBER))
            out.append(self._verified(f"User.role={role}", str(username),
                                      SCOPE_USER, True, "users",
                                      subject="User.role",
                                      observed_value=role,
                                      value_kind=VALUE_KIND_ENUM))
        for oid, uid, status in self._rows(
                "SELECT id, user_id, status FROM orders"):
            out.append(self._verified("Order.exists", str(oid),
                                      SCOPE_RESOURCE, True, "orders",
                                      subject="Order.exists",
                                      value_kind=VALUE_KIND_BOOLEAN))
            out.append(self._verified(f"Order.status={status}", str(oid),
                                      SCOPE_RESOURCE, True, "orders",
                                      subject="Order.status",
                                      observed_value=status,
                                      value_kind=VALUE_KIND_ENUM))
            out.append(self._verified(f"Order.user_id={uid}", str(oid),
                                      SCOPE_RESOURCE, True, "orders",
                                      subject="Order.user_id",
                                      observed_value=uid,
                                      value_kind=VALUE_KIND_NUMBER))
        for code, used in self._rows(
                "SELECT code, used FROM coupons"):
            out.append(self._verified("Coupon.used", str(code),
                                      SCOPE_RESOURCE, bool(used), "coupons",
                                      subject="Coupon.used",
                                      observed_value=bool(used),
                                      value_kind=VALUE_KIND_BOOLEAN))
        return out




def observe_request_auth(token, app_module, db_path):
    
    import hmac as _hmac

    if not token or not isinstance(token, str):
        return None
    username, _, sig = token.partition(":")
    if not username or not sig:
        return None
    expected = app_module.make_token(username)
    if not _hmac.compare_digest(expected, token):
        return None
    probe = VulnshopStateObserver(db_path)
    present = username in {str(r[0]) for r in probe._rows(
        "SELECT username FROM users")}     
    if not present:
        return None
    return StateObservation(
        key=StateKey("RequestAuth.subject", "request", SCOPE_USER),
        value=True, evidence=Evidence.RUNTIME_VERIFIED, source="probe:auth",
        subject="RequestAuth.subject", observed_value=username,
        value_kind=VALUE_KIND_ENUM)
