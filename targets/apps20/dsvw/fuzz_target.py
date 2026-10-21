from stateforge.targets.apps20.dsvw.harness import (  
    _CONN as CONN,
)

class LoopbackAdapter:
    

    def execute(self, data: bytes) -> object:
        import json

        try:
            seed = json.loads(data) if data else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            seed = {}
        if not isinstance(seed, dict):
            seed = {}
        method = str(seed.get("method", "GET")).upper()
        path = str(seed.get("path", "/"))
        try:
            CONN.request(method, path)
            resp = CONN.getresponse()
            resp.read()
            return resp
        except Exception:                       
            return None


_ADAPTER = LoopbackAdapter()

def target(data: bytes) -> None:
    _ADAPTER.execute(data)


if __name__ == "__main__":
    import atheris

    atheris.Setup([], target)
    atheris.Fuzz()
