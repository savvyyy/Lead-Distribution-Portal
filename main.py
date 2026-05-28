"""Lead Distribution Portal — FastAPI backend.

Routes:
  GET  /              -> public form
  GET  /dashboard     -> internal dashboard
  POST /api/leads     -> ingest new lead
  GET  /api/leads     -> list all leads
  GET  /api/stats     -> aggregate stats
  GET  /api/hubspot   -> router status
  POST /api/hubspot/toggle -> toggle router connection
  WS   /ws            -> real-time event stream
"""
import asyncio
import json
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from hubspot_client import hubspot
from datetime import datetime

from models import (
    BUDGET_TO_VALUE,
    HubSpotStatus,
    Lead,
    LeadInput,
    LocalStatus,
    SyncAttempt,
)
import storage

load_dotenv()

app = FastAPI(title="Lead Distribution Portal")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------- WebSocket broadcaster ----------
class Broadcaster:
    def __init__(self):
        self._clients: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._clients.append(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self._clients:
                self._clients.remove(ws)

    async def broadcast(self, event: dict):
        msg = json.dumps(event, default=str)
        dead = []
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


bus = Broadcaster()


# ---------- Pages ----------
@app.get("/")
async def form_page():
    return FileResponse(STATIC_DIR / "form.html")


@app.get("/dashboard")
async def dashboard_page():
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/logs")
async def logs_page():
    return FileResponse(STATIC_DIR / "logs.html")


# ---------- API ----------
@app.post("/api/leads")
async def create_lead(payload: dict):
    # Validate
    try:
        validated = LeadInput(**payload)
    except ValidationError as e:
        errs = e.errors()
        msg = errs[0].get("msg", "Invalid input") if errs else "Invalid input"
        # Strip non-serializable ctx (e.g. raw ValueError) from details
        safe_details = [
            {k: v for k, v in err.items() if k != "ctx"} for err in errs
        ]
        return JSONResponse(status_code=400, content={"error": msg, "details": safe_details})

    # Build lead
    lead = Lead(
        first_name=validated.first_name.strip(),
        last_name=validated.last_name.strip(),
        email=validated.email,
        company=validated.company.strip(),
        budget=validated.budget,
        estimated_value=BUDGET_TO_VALUE[validated.budget],
        local_status=LocalStatus.VALIDATED,
        hubspot_status=HubSpotStatus.PENDING,
    )
    await storage.add_lead(lead)
    await bus.broadcast({"type": "lead.created", "lead": lead.model_dump()})

    # Fire async HubSpot sync
    asyncio.create_task(_sync_to_hubspot(lead.id))

    return {"ok": True, "lead": lead.model_dump()}


async def _sync_to_hubspot(lead_id: str):
    lead = await storage.get_lead(lead_id)
    if not lead:
        return

    # Mark syncing
    lead = await storage.update_lead(lead_id, hubspot_status=HubSpotStatus.SYNCING.value)
    if lead:
        await bus.broadcast({"type": "lead.updated", "lead": lead.model_dump()})

    success, contact_id, err = await hubspot.create_contact(
        first_name=lead.first_name,
        last_name=lead.last_name,
        email=lead.email,
        company=lead.company,
        budget=lead.budget.value,
    )

    # Append sync attempt to history
    fresh = await storage.get_lead(lead_id)
    attempts = list(fresh.sync_attempts) if fresh else []
    attempt = SyncAttempt(
        attempt=len(attempts) + 1,
        success=success,
        contact_id=contact_id,
        error=err,
        mode=hubspot.mode,
    )
    attempts.append(attempt)
    attempts_payload = [a.model_dump() for a in attempts]

    if success:
        lead = await storage.update_lead(
            lead_id,
            hubspot_status=HubSpotStatus.SYNCED.value,
            hubspot_contact_id=contact_id,
            hubspot_error=None,
            sync_attempts=attempts_payload,
            updated_at=datetime.utcnow().isoformat(),
        )
    else:
        lead = await storage.update_lead(
            lead_id,
            hubspot_status=HubSpotStatus.FAILED.value,
            hubspot_error=err,
            sync_attempts=attempts_payload,
            updated_at=datetime.utcnow().isoformat(),
        )
    if lead:
        await bus.broadcast({"type": "lead.updated", "lead": lead.model_dump()})
        await bus.broadcast({
            "type": "sync.attempt",
            "lead_id": lead_id,
            "lead_name": f"{lead.first_name} {lead.last_name}",
            "lead_email": lead.email,
            "attempt": attempt.model_dump(),
        })


@app.get("/api/leads")
async def list_leads():
    leads = await storage.list_leads()
    # newest first
    leads.sort(key=lambda l: l.created_at, reverse=True)
    return {"leads": [l.model_dump() for l in leads]}


@app.post("/api/leads/{lead_id}/retry")
async def retry_lead(lead_id: str):
    lead = await storage.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    # Re-queue sync
    await storage.update_lead(lead_id, hubspot_status=HubSpotStatus.PENDING.value)
    asyncio.create_task(_sync_to_hubspot(lead_id))
    return {"ok": True, "message": "Retry scheduled"}


@app.get("/api/logs")
async def list_logs(only_failed: bool = False):
    """Flattened sync attempt log across all leads, newest first."""
    leads = await storage.list_leads()
    entries = []
    for lead in leads:
        for att in lead.sync_attempts:
            if only_failed and att.success:
                continue
            entries.append({
                "at": att.at,
                "attempt": att.attempt,
                "success": att.success,
                "contact_id": att.contact_id,
                "error": att.error,
                "mode": att.mode,
                "lead_id": lead.id,
                "lead_name": f"{lead.first_name} {lead.last_name}",
                "lead_email": lead.email,
                "lead_company": lead.company,
            })
    entries.sort(key=lambda e: e["at"], reverse=True)
    return {"entries": entries}


@app.get("/api/stats")
async def stats():
    leads = await storage.list_leads()
    total = len(leads)
    pipeline = sum(l.estimated_value for l in leads)
    synced = sum(1 for l in leads if l.hubspot_status == HubSpotStatus.SYNCED)
    failed = sum(1 for l in leads if l.hubspot_status == HubSpotStatus.FAILED)
    return {
        "total_leads": total,
        "pipeline_value": pipeline,
        "synced_count": synced,
        "failed_count": failed,
    }


@app.get("/api/hubspot")
async def hubspot_status():
    return hubspot.status()


@app.post("/api/hubspot/toggle")
async def toggle_hubspot():
    hubspot.set_connected(not hubspot.connected)
    status = hubspot.status()
    await bus.broadcast({"type": "hubspot.status", "status": status})
    return status


# ---------- WebSocket ----------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await bus.connect(ws)
    try:
        # Send initial state
        leads = await storage.list_leads()
        leads.sort(key=lambda l: l.created_at, reverse=True)
        await ws.send_text(json.dumps({
            "type": "snapshot",
            "leads": [l.model_dump() for l in leads],
            "hubspot": hubspot.status(),
        }, default=str))
        while True:
            # Keepalive — clients don't need to send anything
            await ws.receive_text()
    except WebSocketDisconnect:
        await bus.disconnect(ws)
    except Exception:
        await bus.disconnect(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
