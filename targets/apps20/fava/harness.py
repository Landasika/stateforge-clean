from __future__ import annotations
import os
import tempfile
from pathlib import Path
REPO = Path(__file__).resolve().parents[4] / "external" / "fava"
_TMPDIR = Path(tempfile.mkdtemp(prefix=f"fava-harness-{os.getpid()}-"))
LEDGER_FILE = _TMPDIR / "ledger.beancount"
LEDGER_FILE.write_text(
    'option "title" "Harness Ledger"\n'
    "2020-01-01 open Assets:Cash\n"
    "2020-01-01 open Assets:Bank:Checking\n"
    "2020-01-01 open Expenses:Food\n"
    "2020-01-01 open Income:Salary\n"
    '2020-01-15 * "Grocery Store" "weekly shopping"\n'
    "  Expenses:Food  45.20 USD\n"
    "  Assets:Cash\n"
    '2020-02-01 * "Employer" "salary"\n'
    "  Assets:Bank:Checking  2000.00 USD\n"
    "  Income:Salary\n"
    "2021-01-01 close Assets:Cash\n",
    encoding="utf-8",
)

from fava.application import create_app          

APP = create_app([str(LEDGER_FILE)], load=True)
CLIENT = APP.test_client()


SLUG = APP.config["LEDGERS"].first_slug()

_ACCOUNT = "Assets:Cash"          
_REF = f"/{SLUG}/journal/"        


ROUTES: list[tuple[str, str] | tuple[str, str, dict[str, str]]] = [
    ("GET", "/"),                                   
    ("GET", f"/{SLUG}/"),
    ("GET", f"/{SLUG}/income_statement/"),
    ("GET", f"/{SLUG}/balance_sheet/"),
    ("GET", f"/{SLUG}/trial_balance/"),
    ("GET", f"/{SLUG}/journal/"),
    ("GET", f"/{SLUG}/journal/?account={_ACCOUNT}"),   
    ("GET", f"/{SLUG}/query/"),
    ("GET", f"/{SLUG}/query/?query_string=balances"),  
    ("GET", f"/{SLUG}/commodities/"),
    ("GET", f"/{SLUG}/documents/"),
    ("GET", f"/{SLUG}/events/"),
    ("GET", f"/{SLUG}/holdings/"),
    ("GET", f"/{SLUG}/holdings/by_currency/"),
    ("GET", f"/{SLUG}/editor/"),
    ("GET", f"/{SLUG}/errors/"),
    ("GET", f"/{SLUG}/statistics/"),
    ("GET", f"/{SLUG}/options/"),
    ("GET", f"/{SLUG}/import/"),
    ("GET", f"/{SLUG}/help/"),
    ("GET", f"/{SLUG}/account/{_ACCOUNT}/"),
    ("GET", f"/{SLUG}/account/Nope:Nope/"),        
    ("GET", f"/{SLUG}/context/?entry_hash=none"),  
    ("GET", f"/{SLUG}/document/?filename=nope"),   
    ("GET", f"/{SLUG}/download-journal/"),
    ("GET", "/jump?time=year", {"Referer": _REF}),         
    ("GET", "/jump?account=" + _ACCOUNT, {"Referer": _REF + "?time=year"}),
    ("GET", f"/{SLUG}/api/changed"),
    ("GET", f"/{SLUG}/api/errors"),
    ("GET", "/nonexistent"),                       
]


def smoke() -> list[tuple[str, int | str]]:
    out = []
    for route in ROUTES:
        method, path = route[0], route[1]
        headers = route[2] if len(route) > 2 else {}
        try:
            r = CLIENT.open(path, method=method, headers=headers)
            out.append((f"{method} {path}", r.status_code))
        except Exception as exc:                   
            out.append((f"{method} {path}",
                        f"EXC:{type(exc).__name__}:{exc}"))
    return out


if __name__ == "__main__":
    results = smoke()
    ok = sum(1 for _, s in results if isinstance(s, int) and s < 500)
    print(f"smoke: {ok}/{len(results)} non-5xx (slug={SLUG})")
    for route, status in results:
        print(f"  {status!s:>4}  {route}")
