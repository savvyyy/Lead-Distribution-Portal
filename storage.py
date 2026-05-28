import json
from typing import List, Optional
from models import Lead

# In-memory database replacement for Vercel's read-only environment
_MEMORY_DB = []

async def list_leads() -> List[Lead]:
    """Returns all leads currently stored in memory."""
    return _MEMORY_DB

async def get_lead(lead_id: str) -> Optional[Lead]:
    """Finds a specific lead by its ID from memory."""
    for lead in _MEMORY_DB:
        if lead.id == lead_id:
            return lead
    return None

async def add_lead(lead: Lead) -> None:
    """Adds a new lead directly into memory."""
    _MEMORY_DB.append(lead)

async def update_lead(lead_id: str, **kwargs) -> Optional[Lead]:
    """Updates fields on an existing lead inside memory."""
    for lead in _MEMORY_DB:
        if lead.id == lead_id:
            for key, value in kwargs.items():
                if hasattr(lead, key):
                    setattr(lead, key, value)
            return lead
    return None