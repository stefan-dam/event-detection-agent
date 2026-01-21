# AI Event Detection Agent

This project implements a small AI agent that reads a traveler's preferences and a
structured itinerary, then generates hazard alerts and opportunity notifications.
It asks for approval and writes approved changes to `outputs/itinerary_changes.txt`.

## Features
- Combines free-text preferences and structured itinerary data.
- Uses a web search + scraper tool for external evidence.
- Stores memory/state to avoid duplicate alerts.
- CLI workflow that collects approvals and writes change list.

## Setup
1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set your Groq API key:
   Windows (PowerShell):
   ```powershell
   $env:GROQ_API_KEY="your_key_here"
   ```
   Optional model override:
   ```powershell
   $env:GROQ_MODEL="llama-3.1-70b-versatile"
   ```
   Optional official hazard domains (comma-separated):
   ```powershell
   $env:OFFICIAL_DOMAINS="weather.gc.ca,travel.gc.ca,weather.gov"
   ```
   macOS/Linux:
   ```bash
   export GROQ_API_KEY=your_key_here
   export GROQ_MODEL=llama-3.1-70b-versatile
   ```
   Optional official hazard domains (comma-separated):
   ```bash
   export OFFICIAL_DOMAINS=weather.gc.ca,travel.gc.ca,weather.gov
   ```
   If unset, a default official domain list is used (see `src/tools.py`).

   Optional web settings:
   ```powershell
   $env:WEB_TIMEOUT="20"
   $env:WEB_RETRIES="3"
   ```
   ```bash
   export WEB_TIMEOUT=20
   export WEB_RETRIES=3
   ```

## Itinerary.xlsx format
Required columns (after normalization/mapping):
- `day`
- `date` (YYYY-MM-DD)
- `start_time`
- `end_time`
- `city`

Recommended/optional columns:
- `activity_type`
- `activity_description`
- `location_area`
- `notes`

Example row:

| day | date       | start_time | end_time | city    | location_area | activity_type | activity_description | notes |
|-----|------------|------------|----------|---------|---------------|---------------|----------------------|-------|
| 1   | 2026-02-03 | 10:00      | 17:00    | Sapporo | Station area  | Sightseeing  | Underground malls    | Avoid late night |

## Quickstart (Interactive Approval Demo)
This is the primary end-to-end path for grading: it prompts for approval and
writes `outputs/itinerary_changes.txt`.

```bash
python -m src.main ^
  --preferences data/User_prefrences.docx ^
  --itinerary data/Itinerary.xlsx ^
  --output outputs/itinerary_changes.txt ^
  --state outputs/state.json ^
  --json-output outputs/itinerary_changes.json
```

## Run (Backend Service)
Start the API:
```bash
uvicorn src.service:app --host 0.0.0.0 --port 8000
```

Example requests:
1) Detect events:
```bash
curl -X POST http://localhost:8000/detect-events ^
  -H "Content-Type: application/json" ^
  -d "{\"preferences_path\":\"data/User_prefrences.docx\",\"itinerary_path\":\"data/Itinerary.xlsx\"}"
```

2) Approve/reject changes (client-driven approval flow):
```bash
curl -X POST http://localhost:8000/approve ^
  -H "Content-Type: application/json" ^
  -d "{\"event_id\":\"evt_123\",\"approved\":true}"
```

```bash
curl http://localhost:8000/state
```
Outputs are written after approvals are recorded.

Optional: detect + approve in one call:
```bash
curl -X POST http://localhost:8000/detect-events-with-approvals ^
  -H "Content-Type: application/json" ^
  -d "{\"preferences_path\":\"data/User_prefrences.docx\",\"itinerary_path\":\"data/Itinerary.xlsx\",\"approvals\":{\"evt_123\":true}}"
```

Optional: backend-only approval flow:
```bash
curl http://localhost:8000/next-approval
```

```bash
curl -X POST http://localhost:8000/submit-approval ^
  -H "Content-Type: application/json" ^
  -d "{\"event_id\":\"evt_123\",\"approved\":true}"
```

## API Contract (examples)
Detect events request:
```json
{
  "preferences_path": "data/User_prefrences.docx",
  "itinerary_path": "data/Itinerary.xlsx",
  "sheet_name": null,
  "max_events": 8
}
```

Detect events response (truncated):
```json
{
  "events": [
    {
      "id": "evt_123",
      "category": "hazard",
      "title": "Heavy snow warning",
      "location": "Sapporo",
      "date": "2026-02-03",
      "sources": [
        {
          "title": "Advisory",
          "url": "https://example.gov/advisory",
          "snippet": "Heavy snow expected..."
        }
      ]
    }
  ]
}
```

Approve request:
```json
{ "event_id": "evt_123", "approved": true }
```

Approve response:
```json
{ "status": "ok", "event_id": "evt_123", "approved": true }
```

Detect + approve request:
```json
{
  "preferences_path": "data/User_prefrences.docx",
  "itinerary_path": "data/Itinerary.xlsx",
  "approvals": { "evt_123": true }
}
```

Detect + approve response (truncated):
```json
{
  "events": { "events": [ { "id": "evt_123" } ] },
  "approvals_applied": { "evt_123": true }
}
```

Outputs are written to `outputs/itinerary_changes.txt`,
`outputs/itinerary_changes.json`, and `outputs/Itinerary_updated.xlsx`.
The text output contains approved changes only.

## Tests
```bash
pytest
```

## Non-interactive Smoke Test (Auto-approves)
```bash
python scripts/smoke_test.py
```
This auto-approves all events to validate wiring; use the CLI or API approval
endpoints to satisfy the approval requirement.

## Example Outputs
See `outputs/example_run.txt` and `outputs/example_run.json` for sample output
formats.

## Run (CLI)
Windows (PowerShell):
```bash
python -m src.main ^
  --preferences data/User_prefrences.docx ^
  --itinerary data/Itinerary.xlsx ^
  --output outputs/itinerary_changes.txt ^
  --state outputs/state.json ^
  --json-output outputs/itinerary_changes.json
```

macOS/Linux:
```bash
python -m src.main \
  --preferences data/User_prefrences.docx \
  --itinerary data/Itinerary.xlsx \
  --output outputs/itinerary_changes.txt \
  --state outputs/state.json \
  --json-output outputs/itinerary_changes.json
```

Optional:
- `--sheet` to specify an Excel sheet name.

The CLI will print each detected event and ask for approval. The text output
contains approved changes only; the JSON output includes approved and rejected
records.
If approved changes are present, an updated itinerary is written to
`outputs/Itinerary_updated.xlsx`.

## Notes
- Internet access is required for live web search/scraping.
- If you run multiple times, `outputs/state.json` stores detected events and
  approvals.
- Official hazard sources are configurable via `OFFICIAL_DOMAINS`; defaults are
  provided if unset.
- Scraping is best-effort with timeouts and may fail due to site changes or rate limits.
- If `requests-cache` is installed, HTTP responses are cached for 1 hour.
