from stateforge.adapters.wsgi import wsgi_adapter  
from stateforge.targets.apps20.trac.harness import APP

_ADAPTER = wsgi_adapter(APP)


def target(data: bytes) -> None:
    _ADAPTER.execute(data)


if __name__ == "__main__":
    import atheris

    atheris.Setup([], target)
    atheris.Fuzz()
