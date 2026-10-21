import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from stateforge.targets.vulnshop import adapter, app as vshop  

if __name__ == "__main__":
    guards, port, db = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    flask_app = vshop.create_app(db_path=db, guards=guards, init_db=True)
    server = adapter._make_server(flask_app, "127.0.0.1", port)
    print(f"[serve] guards={guards} port={port}", flush=True)
    server.serve_forever()
