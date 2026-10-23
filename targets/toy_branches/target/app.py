from flask import Flask, jsonify, request

app = Flask(__name__)


def deep_target(choice: int, a: int, b: int):
    if choice == 0:
        if a > 20:
            if b > 100:
                return "TARGET_REACHED"
        return "NOT_REACHED"
    if choice == 1:
        return "NOT_REACHED"
    if choice == 2:
        return "NOT_REACHED"
    return "NOT_REACHED"


@app.post("/check")
def check():
    data = request.get_json(silent=True) or {}
    values = [data.get(name, 0) for name in ("choice", "a", "b")]
    values = [value if isinstance(value, int) else 0 for value in values]
    return jsonify({"result": deep_target(*values)})
