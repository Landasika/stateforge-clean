from __future__ import annotations
import hmac
import os
import sqlite3
from flask import Flask, jsonify, request
from .app import (
    DB_PATH,
    TOKEN_SECRET,
    _bad_request,
    connect,
    init_database,
    make_token,
)


def create_anota_app(db_path: str = None, init_db: bool = True) -> Flask:
    app = Flask(__name__)
    app.config.update(GUARDS=0, DB_PATH=db_path or DB_PATH, ANOTA=True)
    if init_db:
        init_database(app.config["DB_PATH"])

    def db():
        return connect(app.config["DB_PATH"])

    def current_user():
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        token = header[len("Bearer "):]
        username, _, sig = token.partition(":")
        if not username or not sig:
            return None
        if not hmac.compare_digest(make_token(username), token):
            return None
        return db().execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()

    def require_user():
        user = current_user()
        if user is None:
            return None, (jsonify({"error": "unauthorized"}), 401)
        return user, None

    def get_order_or_none(oid: int):
        return db().execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()

    @app.errorhandler(RuntimeError)
    def anota_channel(exc):  
        return jsonify({"error": str(exc), "anota": True}), 500

    @app.get("/")
    def index():
        return jsonify({"app": "vulnshop-anota", "guards": 0})

    @app.post("/auth/register")
    def register():
        body = request.get_json(silent=True) or {}
        username, password = body.get("username"), body.get("password")
        if not isinstance(username, str) or not username or not isinstance(password, str) or not password:
            return _bad_request("username/password required")
        try:
            cur = db().execute(
                "INSERT INTO users(username, password, role) VALUES(?, ?, 'user')",
                (username, password),
            )
        except sqlite3.IntegrityError:
            return jsonify({"error": "username exists"}), 409
        return jsonify({"id": cur.lastrowid, "username": username, "role": "user"}), 201

    @app.post("/auth/login")
    def login():
        body = request.get_json(silent=True) or {}
        row = db().execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (body.get("username"), body.get("password")),
        ).fetchone()
        if row is None:
            return jsonify({"error": "bad credentials"}), 401
        return jsonify({"token": make_token(row["username"])})

    @app.get("/auth/me")
    def me():
        user, err = require_user()
        if err:
            return err
        return jsonify({"id": user["id"], "username": user["username"], "role": user["role"]})

    @app.post("/orders")
    def create_order():
        user, err = require_user()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        items = body.get("items")
        if not isinstance(items, list) or not items:
            return _bad_request("items required")
        total = 0
        for item in items:
            price, qty = item.get("price"), item.get("qty")
            if not isinstance(price, int) or price <= 0 or not isinstance(qty, int) or qty <= 0:
                return _bad_request("bad price/qty")
            total += price * qty

        coupon_code = body.get("coupon_code")
        if coupon_code is not None:
            coupon = db().execute(
                "SELECT * FROM coupons WHERE code=?", (coupon_code,)
            ).fetchone()
            if coupon is None:
                return jsonify({"error": "coupon not found"}), 404
            
            ANOTA_EXECUTION.BLOCK(not coupon["used"], msg="ANOTA_POLICY:coupon_single_use")
            total -= coupon["discount"]
            db().execute(
                "UPDATE coupons SET used=1, user_id=? WHERE code=?",
                (user["id"], coupon_code),
            )

        cur = db().execute(
            "INSERT INTO orders(user_id, status, total, paid_amount) VALUES(?, 'CREATED', ?, 0)",
            (user["id"], total),
        )
        return (
            jsonify({"id": cur.lastrowid, "status": "CREATED", "total": total, "paid_amount": 0}),
            201,
        )
    @app.get("/orders/<int:oid>")
    def read_order(oid: int):
        user, err = require_user()
        if err:
            return err
        order = get_order_or_none(oid)
        if order is None:
            return jsonify({"error": "order not found"}), 404
        
        ANOTA_EXECUTION.BLOCK(order["user_id"] == user["id"], msg="ANOTA_POLICY:order_owner_read")
        return jsonify(
            {
                "id": order["id"],
                "user_id": order["user_id"],
                "status": order["status"],
                "total": order["total"],
                "paid_amount": order["paid_amount"],
            }
        )

    @app.post("/orders/<int:oid>/pay")
    def pay_order(oid: int):
        user, err = require_user()
        if err:
            return err
        order = get_order_or_none(oid)
        if order is None:
            return jsonify({"error": "order not found"}), 404
        amount = (request.get_json(silent=True) or {}).get("amount")
        if not isinstance(amount, int) or amount <= 0:
            return _bad_request("amount must be positive int")
        
        ANOTA_EXECUTION.BLOCK(order["user_id"] == user["id"], msg="ANOTA_POLICY:order_owner_pay")
        
        ANOTA_EXECUTION.BLOCK(
            order["paid_amount"] + amount >= order["total"], msg="ANOTA_POLICY:pay_full_amount"
        )
        paid = order["paid_amount"] + amount
        db().execute("UPDATE orders SET paid_amount=?, status='PAID' WHERE id=?", (paid, oid))
        return jsonify({"id": oid, "status": "PAID", "paid_amount": paid})

    @app.post("/orders/<int:oid>/ship")
    def ship_order(oid: int):
        user, err = require_user()
        if err:
            return err
        order = get_order_or_none(oid)
        if order is None:
            return jsonify({"error": "order not found"}), 404
        ANOTA_EXECUTION.BLOCK(order["status"] == "PAID", msg="ANOTA_POLICY:ship_requires_paid")
        db().execute("UPDATE orders SET status='SHIPPED' WHERE id=?", (oid,))
        return jsonify({"id": oid, "status": "SHIPPED"})

    @app.post("/orders/<int:oid>/cancel")
    def cancel_order(oid: int):
        user, err = require_user()
        if err:
            return err
        order = get_order_or_none(oid)
        if order is None:
            return jsonify({"error": "order not found"}), 404
        db().execute("UPDATE orders SET status='CANCELLED' WHERE id=?", (oid,))
        return jsonify({"id": oid, "status": "CANCELLED"})

    @app.get("/coupons/<code>")
    def read_coupon(code: str):
        row = db().execute("SELECT * FROM coupons WHERE code=?", (code,)).fetchone()
        if row is None:
            return jsonify({"error": "coupon not found"}), 404
        return jsonify({"code": row["code"], "used": row["used"], "discount": row["discount"]})

    @app.post("/admin/users/<int:uid>/role")
    def set_role(uid: int):
        user, err = require_user()
        if err:
            return err
        
        ANOTA_EXECUTION.BLOCK(user["role"] == "admin", msg="ANOTA_POLICY:admin_required")
        target = db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if target is None:
            return jsonify({"error": "user not found"}), 404
        role = (request.get_json(silent=True) or {}).get("role")
        if not isinstance(role, str) or not role:
            return _bad_request("role required")
        db().execute("UPDATE users SET role=? WHERE id=?", (role, uid))
        return jsonify({"id": uid, "role": role})

    return app
