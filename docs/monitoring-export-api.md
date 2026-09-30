# Monitoring, export, and API

## Drift monitoring

`rosetta monitor INPUT PARSER_NAME` compares an input batch with an active or
verified parser. It reports matched coverage and mean parser confidence. When
coverage falls below `--min-coverage` (default `0.9`) or parser errors occur,
the command writes a report, marks an active parser `drifting`, and creates a
new **draft** parser from unmatched records when usable records are available.
The draft is added to the review list; it is never activated automatically.

```powershell
python -m rosettalog monitor samples\unseen\asa_new.log asa_syslog
```

Input is bounded to 50 MiB, 1,000,000 lines, and 64 KiB per line. The learner
uses at most the first 10,000 unmatched records in a re-learn proposal.

## Event export

`rosetta export EVENTS OUTPUT --format FORMAT` validates each envelope before
exporting `ndjson`, `cef`, or `syslog`. CEF and RFC 5424 output include a
Base64-encoded canonical envelope so raw data, unmapped fields, and lineage can
be recovered without relying on lossy field flattening. The CEF extension uses
`cs1Label=RosettaLogEnvelopeBase64` and `cs1=<value>`. Syslog carries an
equivalent `envelope_base64` field in its JSON message body.

```powershell
python -m rosettalog export data\raw_store\events.jsonl data\events.cef --format cef
```

## Local API and UI

`python -m uvicorn rosettalog.api.app:app --host 127.0.0.1 --port 8000` starts
the FastAPI service. The API exposes health, parser inventory, bounded event
queries, and streamed log uploads. Uploads are capped at 50 MiB by default.
The Streamlit UI is started with:

```powershell
python -m streamlit run src\rosettalog\ui\streamlit_app.py
```

**STUB:** API authentication and authorization. Compose binds both services to loopback and
uses an internal-only bridge network; deploy behind an authenticated boundary
before exposing either port to other hosts.
