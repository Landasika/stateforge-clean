
from stateforge.targets.apps20.vampi.harness import CLIENT, _TOKEN  


def _make_adapter():
    from stateforge.adapters.generic_web import GenericWebAdapter

    adapter = GenericWebAdapter.__new__(GenericWebAdapter)
    adapter.client = CLIENT
    adapter.auth_headers = ({"Authorization": f"Bearer {_TOKEN}"} if _TOKEN
                            else {})
    adapter.base_url = ""
    return adapter


_ADAPTER = _make_adapter()


def target(data: bytes) -> None:
    _ADAPTER.execute(data)


if __name__ == "__main__":
    import atheris

    atheris.Setup([], target)
    atheris.Fuzz()
