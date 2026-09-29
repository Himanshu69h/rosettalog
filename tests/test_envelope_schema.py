import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "envelope.schema.json"
EVENT_PATH = ROOT / "examples" / "sample-event.json"


def test_envelope_validates_against_schema() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    event = json.loads(EVENT_PATH.read_text(encoding="utf-8"))

    jsonschema.validate(instance=event, schema=schema)
