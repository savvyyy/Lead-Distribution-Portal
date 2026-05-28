"""JSON file storage for leads. Thread-safe via asyncio.Lock."""
import asyncio
import json
import os
from pathlib import Path
from typing import List, Optional

from models import Lead

DATA_FILE = Path(os.getenv("LEADS_FILE", "leads.json"))
_lock = asyncio.Lock()


def _read_sync() -> List[dict]:
    if not DATA_FILE.exists():
        return []
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _write_sync(data: List[dict]) -> None:
    tmp = DATA_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    tmp.replace(DATA_FILE)


async def list_leads() -> List[Lead]:
    async with _lock:
        raw = _read_sync()
    return [Lead(**item) for item in raw]


async def add_lead(lead: Lead) -> Lead:
    async with _lock:
        data = _read_sync()
        data.append(lead.model_dump())
        _write_sync(data)
    return lead


async def update_lead(lead_id: str, **changes) -> Optional[Lead]:
    async with _lock:
        data = _read_sync()
        for item in data:
            if item["id"] == lead_id:
                item.update(changes)
                _write_sync(data)
                return Lead(**item)
    return None


async def get_lead(lead_id: str) -> Optional[Lead]:
    async with _lock:
        data = _read_sync()
    for item in data:
        if item["id"] == lead_id:
            return Lead(**item)
    return None
