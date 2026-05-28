import os
import json
from typing import List, Optional
import redis.asyncio as redis
from models import Lead

# Vercel automatically provides the KV_URL environment variable when connected
KV_URL = os.getenv("KV_URL")

# Initialize Redis client
kv = redis.from_url(KV_URL, decode_responses=True) if KV_URL else None

async def list_leads() -> List[Lead]:
    """Fetch all leads stored in the cloud KV database."""
    if not kv:
        return []
    
    # Fetch all lead IDs
    lead_ids = await kv.smembers("leads:ids")
    if not lead_ids:
        return []
    
    # Fetch the data payloads for all lead IDs
    leads_json = await kv.mget([f"lead:{lid}" for lid in lead_ids])
    
    leads = []
    for lj in leads_json:
        if lj:
            leads.append(Lead(**json.loads(lj)))
    return leads

async def get_lead(lead_id: str) -> Optional[Lead]:
    """Fetch a single lead by its ID from the cloud database."""
    if not kv:
        return None
    data = await kv.get(f"lead:{lead_id}")
    return Lead(**json.loads(data)) if data else None

async def add_lead(lead: Lead) -> None:
    """Save a new lead to the cloud database permanently."""
    if not kv:
        return
    lead_id = lead.id
    # Add ID to our index set and store the lead object payload
    await kv.sadd("leads:ids", lead_id)
    await kv.set(f"lead:{lead_id}", json.dumps(lead.model_dump(), default=str))

async def update_lead(lead_id: str, **kwargs) -> Optional[Lead]:
    """Update field properties on an existing lead in the database."""
    if not kv:
        return None
    
    lead = await get_lead(lead_id)
    if not lead:
        return None
        
    for key, value in kwargs.items():
        if hasattr(lead, key):
            setattr(lead, key, value)
            
    await kv.set(f"lead:{lead_id}", json.dumps(lead.model_dump(), default=str))
    return lead