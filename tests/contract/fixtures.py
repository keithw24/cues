import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[2] / "shared/fixtures"


def fixture_rows(name: str, model) -> list[dict]:
    """The shared fixture rows, validated and re-dumped exactly as a producer would send them."""
    rows = json.loads((FIXTURES / name).read_text())
    return [model.model_validate(row).model_dump(mode="json") for row in rows]
