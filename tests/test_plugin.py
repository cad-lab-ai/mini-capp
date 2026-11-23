import json
from pathlib import Path


def test_runtime_payload_matches_sources():
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / "plugin/runtime.json").read_text(encoding="utf-8"))
    for path, content in payload.items():
        assert (root / path).read_text(encoding="utf-8") == content, f"regenerate plugin payload: {path}"
    assert "src/process_planning/templates/route.html" in payload
    tools = json.loads((root / "plugin/tools.json").read_text(encoding="utf-8"))
    assert len(tools) == 12
