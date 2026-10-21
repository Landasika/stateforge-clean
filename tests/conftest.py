import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

for name in [name for name in sys.modules
             if name == "stateforge" or name.startswith("stateforge.")]:
    del sys.modules[name]

spec = importlib.util.spec_from_file_location(
    "stateforge", ROOT / "__init__.py",
    submodule_search_locations=[str(ROOT)])
module = importlib.util.module_from_spec(spec)
sys.modules["stateforge"] = module
spec.loader.exec_module(module)

root_text = str(ROOT)
if root_text not in sys.path:
    sys.path.insert(0, root_text)
