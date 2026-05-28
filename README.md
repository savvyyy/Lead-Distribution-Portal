# Lead Distribution Portal

A lightweight lead-ingestion system: public web form → FastAPI backend → real-time dashboard, with HubSpot CRM sync.

## Architecture

```
[Web Form]  ──POST──►  [FastAPI Backend]  ──WebSocket──►  [Dashboard]
                              │
                              ▼
                       [HubSpot CRM API]
                       (mock or live)
```

## Features

- **Public form** at `/` — collects first/last name, corporate email, company, budget range
- **Internal dashboard** at `/dashboard` — live lead feed, analytics badges, HubSpot router toggle
- **Real-time updates** via WebSocket — new leads appear instantly with sync status transitions (`pending` → `syncing` → `synced`/`failed`)
- **Validation** — Pydantic schema + corporate email check (rejects gmail/yahoo/etc.)
- **HubSpot integration** — async create_contact via `/crm/v3/objects/contacts`; runs in **mock mode** by default, swap to live via env var
- **JSON file persistence** — `leads.json`

## Setup

```bash
cd lead-portal
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # then edit if going live
```

## Run

```bash
python main.py
# or:  uvicorn main:app --reload --port 8000
```

Then open:
- Form:      http://localhost:8000/
- Dashboard: http://localhost:8000/dashboard

## Going live with HubSpot

1. In your HubSpot Sandbox, go to **Settings → Integrations → Private Apps → Create**
2. Grant scopes: `crm.objects.contacts.read`, `crm.objects.contacts.write`
3. Copy the access token into `.env`:
   ```
   HUBSPOT_TOKEN=pat-na1-xxxxxxxx
   HUBSPOT_LIVE=true
   ```
4. Restart the server.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Public form page |
| GET | `/dashboard` | Internal dashboard |
| POST | `/api/leads` | Ingest a new lead (JSON body) |
| GET | `/api/leads` | List all leads |
| GET | `/api/stats` | Aggregate counts + pipeline value |
| GET | `/api/hubspot` | Router connection status |
| POST | `/api/hubspot/toggle` | Toggle router on/off |
| WS | `/ws` | Real-time event stream |

### POST `/api/leads` body
```json
{
  "first_name": "Jane",
  "last_name": "Doe",
  "email": "jane@acme.com",
  "company": "Acme Corp",
  "budget": "$10k-$50k"
}
```

### WebSocket events
```json
{ "type": "snapshot",     "leads": [...], "hubspot": {...} }
{ "type": "lead.created", "lead":  {...} }
{ "type": "lead.updated", "lead":  {...} }
{ "type": "hubspot.status", "status": {...} }
```

## File layout

```
lead-portal/
├── main.py              # FastAPI app + routes + WebSocket
├── models.py            # Pydantic schemas, enums, budget→$ map
├── storage.py           # JSON file CRUD (async, locked)
├── hubspot_client.py    # HubSpot integration (mock + live)
├── static/
│   ├── form.html        # Public submission form
│   └── dashboard.html   # Internal dashboard SPA
├── requirements.txt
├── .env.example
└── README.md
```

## Notes

- Mock mode simulates 0.4–1.2s latency and ~10% failure rate so the dashboard's status transitions are visible.
- Pipeline value uses midpoint estimates: `<$10k = $5k`, `$10k–$50k = $30k`, `>$50k = $75k`.
- All lead state is broadcast over WebSocket — open the dashboard in one tab and the form in another to see real-time flow.
