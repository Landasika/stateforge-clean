import json
from pathlib import Path

from stateforge.analysis.static.icfg import build_icfg

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "targets" / "manifest.json"


def test_acceptance_target_manifest_and_layout():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    names = {item["name"] for item in payload["targets"]}
    assert names == {"vampi", "pygoat", "oscar"}
    for item in payload["targets"]:
        assert (ROOT / item["source_path"]).is_dir()
        assert (ROOT / item["harness"]).is_file()
        assert (ROOT / item["fuzz_target"]).is_file()
        assert (ROOT / item["requirements"]).is_file()
        assert item["upstream"].startswith("https://github.com/")


def test_acceptance_target_sources_produce_icfg():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    minimum = {"vampi": 200, "pygoat": 800, "oscar": 8000}
    for item in payload["targets"]:
        ir = build_icfg(ROOT / item["source_path"])
        assert len(ir.functions) > 0
        assert len(ir.blocks) > minimum[item["name"]]
        assert len(ir.edges) > 0
