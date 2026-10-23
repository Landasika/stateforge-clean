from stateforge.adapters.generic_web import GenericWebAdapter
from targets.vampi.harness import APP, _TOKEN


def _make_adapter():
    headers = {"Authorization": f"Bearer {_TOKEN}"} if _TOKEN else {}
    return GenericWebAdapter(APP, auth_headers=headers)


_ADAPTER = _make_adapter()


def target(data: bytes) -> None:
    _ADAPTER.execute(data)


if __name__ == "__main__":
    import atheris

    atheris.Setup([], target)
    atheris.Fuzz()
