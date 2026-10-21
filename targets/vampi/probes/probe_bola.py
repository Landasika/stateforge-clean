from _probe_lib import call, jbody, register_and_login, run, uniq, verdict
def main() -> int:
    call("GET", "/createdb")
    alice, ta = register_and_login(uniq("alice"))
    bob, tb = register_and_login(uniq("bob"))
    title = uniq("book")
    status, body = call(
        "POST", "/books/v1",
        {"book_title": title, "secret": "TOP-SECRET-42", "username": alice},
        token=ta,
    )
    if status not in (200, 201):
        return verdict("BOLA(book create)", False)
    status, body = call("GET", f"/books/v1/{title}", token=tb)  
    leaked = status == 200 and "TOP-SECRET-42" in body
    return verdict("BOLA(cross-user book secret read)", leaked)

if __name__ == "__main__":
    run(main)
