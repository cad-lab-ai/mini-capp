"""Static HTML templates; all substitutions except generated rows are escaped."""
from pathlib import Path
from string import Template

FIELDS = ("name", "designation", "material", "blank", "rows", "revision", "passport_revision")


def builtin_template() -> str:
    return Path(__file__).with_name("templates").joinpath("route.html").read_text(encoding="utf-8")


def check_template(html: str) -> None:
    if not html.strip() or len(html.encode("utf-8")) > 64_000:
        raise ValueError("template must contain 1..64000 UTF-8 bytes")
    template = Template(html)
    if not template.is_valid():
        raise ValueError("invalid placeholder syntax; use $name or ${name}, and $$ for a literal dollar")
    unknown = set(template.get_identifiers()) - set(FIELDS)
    if unknown:
        raise ValueError(f"unknown placeholders: {', '.join(sorted(unknown))}; allowed: {', '.join(FIELDS)}")
    if "rows" not in template.get_identifiers():
        raise ValueError("template must include $rows to display the route operations")
