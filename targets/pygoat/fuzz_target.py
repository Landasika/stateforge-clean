from stateforge.adapters.generic_web import GenericWebAdapter
from targets.pygoat.harness import CLIENT


def _make_adapter():
    CLIENT.generic = lambda method, path, **kwargs: CLIENT.request(
        REQUEST_METHOD=method, PATH_INFO=path, **kwargs)
    adapter = GenericWebAdapter.__new__(GenericWebAdapter)
    adapter.client = CLIENT
    adapter.auth_headers = {}
    adapter.base_url = ""
    return adapter


_ADAPTER = _make_adapter()


def target(data: bytes) -> None:
    _ADAPTER.execute(data)


if __name__ == "__main__":
    import atheris

    atheris.Setup([], target)
    atheris.Fuzz()
