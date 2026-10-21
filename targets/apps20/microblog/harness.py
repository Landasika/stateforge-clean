from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path
REPO = Path(__file__).resolve().parents[4] / "external" / "microblog"
SF_DB = os.environ.get("SF_DB") or str(
    Path(tempfile.mkdtemp(prefix=f"microblog-harness-{os.getpid()}-"))
    / "microblog.db"
)
os.environ["DATABASE_URL"] = f"sqlite:///{SF_DB}"     
os.environ.setdefault("SECRET_KEY", "stateforge-harness-key")

sys.path.insert(0, str(REPO))       
os.chdir(REPO)                      

from config import Config           


class HarnessConfig(Config):
    
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{SF_DB}"
    TESTING = True                  
    WTF_CSRF_ENABLED = False
    ELASTICSEARCH_URL = None
    MAIL_SERVER = None              
    REDIS_URL = "redis://"          

from app import create_app, db, models   

APP = create_app(HarnessConfig)

with APP.app_context():
    db.create_all()
    if models.User.query.filter_by(username="probe").first() is None:
        user = models.User(username="probe", email="probe@example.com")
        user.set_password("probe-pass")
        user2 = models.User(username="peer", email="peer@example.com")
        user2.set_password("peer-pass")
        post = models.Post(body="hello from harness", author=user)
        db.session.add_all([user, user2, post])
        db.session.commit()

CLIENT = APP.test_client()



class _FakeRQJob:
    def get_id(self) -> str:
        return f"fake-task-{os.getpid()}"


class _FakeTaskQueue:
    def enqueue(self, *args, **kwargs):
        return _FakeRQJob()


APP.task_queue = _FakeTaskQueue()


_LOGIN_R = CLIENT.post("/auth/login",
                       data={"username": "probe", "password": "probe-pass"})
LOGGED_IN = _LOGIN_R.status_code == 302 and b"login" not in _LOGIN_R.data.lower()


_TOKEN = None
try:
    _tok_r = CLIENT.post("/api/tokens", auth=("probe", "probe-pass"))
    if _tok_r.status_code == 200:
        import json as _json
        _TOKEN = _json.loads(_tok_r.data).get("token")
except Exception:                                           
    _TOKEN = None
_BEARER = {"Authorization": f"Bearer {_TOKEN}"} if _TOKEN else {}

ROUTES: list[tuple] = [
    ("GET", "/"),                                  
    ("GET", "/index"),
    ("GET", "/explore"),
    ("GET", "/user/probe"),
    ("GET", "/user/peer"),
    ("GET", "/user/probe/popup"),
    ("GET", "/user/ghost"),                        
    ("GET", "/edit_profile"),
    ("GET", "/messages"),
    ("GET", "/notifications"),
    ("GET", "/search?q=hello"),
    ("GET", "/search?q="),
    ("GET", "/export_posts"),
    ("GET", "/auth/login"),
    ("GET", "/auth/register"),
    ("GET", "/auth/reset_password_request"),
    ("GET", "/api/users", None, _BEARER),          
    ("GET", "/api/users/1", None, _BEARER),
    ("GET", "/api/users/1/followers", None, _BEARER),
    ("GET", "/api/users/1/following", None, _BEARER),
    ("GET", "/api/users"),                         
    ("POST", "/follow/peer"),                      
    ("POST", "/unfollow/peer"),
    ("POST", "/send_message/peer", {"message": "hi from harness"}),
    ("POST", "/edit_profile",
     {"username": "probe", "about_me": "harness was here"}),
    ("POST", "/auth/login", {"username": "probe", "password": "wrong"}),
    ("GET", "/nonexistent"),                       
    ("GET", "/auth/logout"),                       
]


def smoke() -> list[tuple[str, int | str]]:
    out = []
    for route in ROUTES:
        method, path = route[0], route[1]
        form = route[2] if len(route) > 2 else None
        headers = route[3] if len(route) > 3 else None
        try:
            if method == "GET":
                r = CLIENT.get(path, headers=headers)
            elif form is not None:
                r = CLIENT.post(path, data=form)
            else:
                r = CLIENT.post(path)
            out.append((f"{method} {path}", r.status_code))
        except Exception as exc:                   
            out.append((f"{method} {path}",
                        f"EXC:{type(exc).__name__}:{exc}"))
    return out


if __name__ == "__main__":
    results = smoke()
    ok = sum(1 for _, s in results if isinstance(s, int) and s < 500)
    print(f"smoke: {ok}/{len(results)} non-5xx "
          f"(db={SF_DB}, login={'ok' if LOGGED_IN else 'FAIL'})")
    for route, status in results:
        print(f"  {status!s:>4}  {route}")
