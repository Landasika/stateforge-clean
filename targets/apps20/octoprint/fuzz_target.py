
from stateforge.targets.apps20.octoprint.harness import AUTH_HEADERS, CLIENT  


def _make_adapter():
    from stateforge.adapters.generic_web import GenericWebAdapter

    adapter = GenericWebAdapter.__new__(GenericWebAdapter)
    adapter.client = CLIENT
    adapter.auth_headers = dict(AUTH_HEADERS)   
    adapter.base_url = ""
    return adapter


_ADAPTER = _make_adapter()


def target(data: bytes) -> None:
    _ADAPTER.execute(data)


if __name__ == "__main__":
    import atheris

    atheris.Setup([], target)
    atheris.Fuzz()
