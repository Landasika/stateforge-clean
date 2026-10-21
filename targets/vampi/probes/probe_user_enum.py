from _probe_lib import call, jbody, run, uniq, verdict
def main() -> int:
    call("GET", "/createdb")
    user = uniq("enum")
    call("POST", "/users/v1/register",
         {"username": user, "password": "right-pw", "email": f"{user}@x.io"})
    msgs = {}
    for label, body in [
        ("ok", {"username": user, "password": "right-pw"}),
        ("wrong-pw", {"username": user, "password": "bad-pw"}),
        ("no-user", {"username": uniq("ghost"), "password": "whatever"}),
    ]:
        _, resp = call("POST", "/users/v1/login", body)
        msgs[label] = jbody(resp).get("message", resp)
    distinguishable = len({msgs["ok"], msgs["wrong-pw"], msgs["no-user"]}) >= 2 and (
        msgs["wrong-pw"] != msgs["no-user"]
    )
    return verdict("user/password enumeration", distinguishable)


if __name__ == "__main__":
    run(main)
