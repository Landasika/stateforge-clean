from flask import Flask, jsonify, request

app = Flask(__name__)


def gate(c: int, d: int):
    if c > 150:
        if d > 200:
            return "TARGET_REACHED"
    return "NOT_REACHED"


def deep_target(a: int, b: int, c: int, d: int):
    if a > 20:
        if b > 100:
            return gate(c, d)
    return "NOT_REACHED"


@app.post("/check")
def check():
    data = request.get_json(silent=True) or {}
    values = [data.get(name, 0) for name in ("a", "b", "c", "d")]
    values = [value if isinstance(value, int) else 0 for value in values]
    return jsonify({"result": deep_target(*values)})
