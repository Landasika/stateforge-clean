from stateforge.adapters.wsgi import wsgi_adapter  
from stateforge.targets.apps20.radicale.harness import APP, _AUTH

def _make_adapter():
    return wsgi_adapter(APP, auth_headers={"Authorization": _AUTH})


_ADAPTER = _make_adapter()


def target(data: bytes) -> None:
    _ADAPTER.execute(data)


if __name__ == "__main__":
    import atheris

    atheris.Setup([], target)
    atheris.Fuzz()
