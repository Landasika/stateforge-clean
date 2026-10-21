from __future__ import annotations
import os
import tempfile
from pathlib import Path
from stateforge.adapters.wsgi import wsgi_adapter
_USER, _PASS = "probe", "passw0rd"

_STORAGE = Path(tempfile.mkdtemp(prefix=f"radicale_store_{os.getpid()}_"))
_HTPASSWD = _STORAGE.parent / f"radicale_htpasswd_{os.getpid()}"

_HTPASSWD.write_text(f"{_USER}:{_PASS}\n", encoding="utf-8")

from radicale import app as radicale_app  
from radicale import config as radicale_config  

_configuration = radicale_config.load()
_configuration.update({
    "storage": {"filesystem_folder": str(_STORAGE)},
    "auth": {"type": "htpasswd", "htpasswd_filename": str(_HTPASSWD),
             "htpasswd_encryption": "plain"},
    "rights": {"type": "owner_only"},
    "headers": {},
}, "harness")
APP = radicale_app.Application(_configuration)

_AUTH = ("Basic " + __import__("base64").b64encode(
    f"{_USER}:{_PASS}".encode()).decode())
ADAPTER = wsgi_adapter(APP, auth_headers={"Authorization": _AUTH})

_CAL = "probe-cal"
_CAL2 = "probe-cal-2"
_EVT = "probe-evt.ics"
_EVT_BODY = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "PRODID:-//StateForge probe//EN\r\n"
    "BEGIN:VEVENT\r\n"
    f"UID:{_EVT}\r\n"
    "DTSTAMP:20260101T000000Z\r\n"
    "DTSTART:20260102T000000Z\r\n"
    "DTEND:20260103T000000Z\r\n"
    "SUMMARY:probe event\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)

ROUTES: list[tuple[str, str, str]] = [
    ("GET", "/.web", "public"),                    
    ("GET", "/.web/index.html", "public"),
    ("GET", "/.web/favicon.png", "public"),
    ("GET", "/", "auth"),
    ("PROPFIND", "/", "auth"),                     
    ("PROPFIND", f"/{_USER}/", "auth"),            
    ("REPORT", f"/{_USER}/", "auth"),              
    ("OPTIONS", "/", "auth"),                      
    ("MKCOL", f"/{_USER}/{_CAL}/", "auth"),        
    ("PROPFIND", f"/{_USER}/{_CAL}/", "auth"),
    ("REPORT", f"/{_USER}/{_CAL}/", "auth"),       
    ("PUT", f"/{_USER}/{_CAL}/{_EVT}", "auth"),    
    ("GET", f"/{_USER}/{_CAL}/{_EVT}", "auth"),    
    ("PROPFIND", f"/{_USER}/{_CAL2}/", "auth"),    
    ("REPORT", f"/{_USER}/{_CAL2}/", "auth"),
    ("PUT", f"/{_USER}/{_CAL2}/{_EVT}", "auth"),
    ("GET", f"/{_USER}/{_CAL2}/{_EVT}", "auth"),
    ("DELETE", f"/{_USER}/{_CAL}/{_EVT}", "auth"),
    ("GET", "/nope/", "auth"),                     
    ("PROPFIND", "/nope/", "auth"),
    ("GET", f"/other-user/", "auth"),              
    ("PROPFIND", f"/other-user/{_CAL}/", "auth"),
]

def smoke() -> list[tuple[str, int]]:
    out = []
    for method, path, auth in ROUTES:
        try:
            headers = {"Authorization": _AUTH} if auth == "auth" else {}
            if method == "GET":
                resp = ADAPTER.client.get(path, headers=headers)
                code = resp.status_code
            else:
                from werkzeug.test import create_environ, run_wsgi_app

                env = create_environ(method=method, path=path,
                                     headers=list(headers.items()))
                if method in ("PUT",):
                    env["wsgi.input"] = __import__("io").BytesIO(
                        _EVT_BODY.encode())
                    env["CONTENT_LENGTH"] = str(len(_EVT_BODY))
                if method in ("PROPFIND", "REPORT"):
                    body = ('<?xml version="1.0"?>'
                            '<d:propfind xmlns:d="DAV:">'
                            '<d:prop><d:resourcetype/><d:getetag/></d:prop>'
                            '</d:propfind>')
                    env["wsgi.input"] = __import__("io").BytesIO(
                        body.encode())
                    env["CONTENT_LENGTH"] = str(len(body))
                app_iter, status, _hdrs = run_wsgi_app(APP, env)
                list(app_iter) if hasattr(app_iter, "__iter__") else None
                code = int(str(status).split()[0])
            out.append((f"{method} {path}", code))
        except Exception as exc:                  
            out.append((f"{method} {path}", f"EXC:{type(exc).__name__}:{exc}"))
    return out


if __name__ == "__main__":
    results = smoke()
    ok = sum(1 for _, s in results if isinstance(s, int) and 100 <= s < 500
             and s != 401 or (isinstance(s, int) and 100 <= s < 500))
    print(f"smoke: {ok}/{len(results)} non-5xx storage={_STORAGE}")
    for route, status in results:
        print(f"  {status!s:>4}  {route}")
