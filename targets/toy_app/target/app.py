from flask import Flask, jsonify, request

app = Flask(__name__)


def deep_target(x: int, y: int):
    if x > 20:
        if y > 100:
            return "TARGET_REACHED"
    return "NOT_REACHED"


@app.post("/check")
def check():
    data = request.get_json(silent=True) or {}
    x = data.get("x", 0)
    y = data.get("y", 0)
    if not isinstance(x, int):
        x = 0
    if not isinstance(y, int):
        y = 0
    return jsonify({"result": deep_target(x, y)})
