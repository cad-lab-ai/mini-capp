"""Regenerate the standalone BB adapter payload from the Python service."""
import asyncio
import json
from pathlib import Path

from process_planning.server import mcp

ROOT = Path(__file__).resolve().parents[1]


async def main():
    files = [ROOT / "pyproject.toml", ROOT / "uv.lock"]
    files += [p for p in (ROOT / "src").rglob("*") if p.is_file() and p.suffix in (".py", ".html")]
    payload = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8") for p in sorted(files)}
    (ROOT / "plugin/runtime.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tools = [t.model_dump(mode="json", exclude_none=True) for t in await mcp.list_tools()]
    (ROOT / "plugin/tools.json").write_text(json.dumps(tools, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
