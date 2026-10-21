
from stateforge.targets.apps20.fava.harness import CLIENT, SLUG  


def _make_adapter():
    from stateforge.adapters.generic_web import GenericWebAdapter

    adapter = GenericWebAdapter.__new__(GenericWebAdapter)
    adapter.client = CLIENT           
    adapter.auth_headers = {}         
    adapter.base_url = f"/{SLUG}"     
    return adapter


_ADAPTER = _make_adapter()


def target(data: bytes) -> None:
    _ADAPTER.execute(data)


if __name__ == "__main__":
    import atheris

    atheris.Setup([], target)
    atheris.Fuzz()
