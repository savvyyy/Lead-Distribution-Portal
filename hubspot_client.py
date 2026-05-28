"""HubSpot CRM client. Supports mock mode and real HubSpot API.

Toggle with HUBSPOT_LIVE env var:
  HUBSPOT_LIVE=false  -> mock (random success/fail, simulated latency)
  HUBSPOT_LIVE=true   -> hits real HubSpot CRM API (requires HUBSPOT_TOKEN)
"""
import asyncio
import os
import random
import uuid
from typing import Optional, Tuple

import httpx

HUBSPOT_BASE = "https://api.hubapi.com"
CONTACTS_ENDPOINT = f"{HUBSPOT_BASE}/crm/v3/objects/contacts"


class HubSpotClient:
    def __init__(self):
        self.token: Optional[str] = os.getenv("HUBSPOT_TOKEN") or None
        self.live: bool = os.getenv("HUBSPOT_LIVE", "false").lower() == "true"
        # Router connection state (toggleable from dashboard)
        self.connected: bool = True
        self.mode: str = "live" if (self.live and self.token) else "mock"

    # ---------- Router control ----------
    def set_connected(self, value: bool) -> None:
        self.connected = bool(value)

    def status(self) -> dict:
        return {
            "connected": self.connected,
            "mode": self.mode,
            "has_token": bool(self.token),
        }

    # ---------- Contact creation ----------
    async def create_contact(
        self,
        first_name: str,
        last_name: str,
        email: str,
        company: str,
        budget: str,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Returns (success, hubspot_contact_id, error_message)."""
        if not self.connected:
            return False, None, "HubSpot router is disconnected"

        if self.mode == "live":
            return await self._create_live(first_name, last_name, email, company, budget)
        return await self._create_mock(first_name, last_name, email, company, budget)

    async def _create_mock(
        self, first_name, last_name, email, company, budget
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        # Simulate network latency
        await asyncio.sleep(random.uniform(0.4, 1.2))
        # 90% success rate
        if random.random() < 0.90:
            fake_id = f"mock-{uuid.uuid4().hex[:12]}"
            return True, fake_id, None
        return False, None, "Mock API: simulated transient failure"

    async def _create_live(
        self, first_name, last_name, email, company, budget
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        if not self.token:
            return False, None, "HUBSPOT_TOKEN not configured"

        payload = {
            "properties": {
                "firstname": first_name,
                "lastname": last_name,
                "email": email,
                "company": company,
                # Standard HubSpot field for budget; map to lifecyclestage or
                # custom property as needed in your portal.
                "annualrevenue": budget,
            }
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(CONTACTS_ENDPOINT, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                data = resp.json()
                return True, data.get("id"), None
            # 409 = contact already exists - treat as success-ish
            if resp.status_code == 409:
                return True, "existing", "Contact already exists in HubSpot"
            return False, None, f"HubSpot {resp.status_code}: {resp.text[:200]}"
        except httpx.HTTPError as e:
            return False, None, f"HTTP error: {e}"


# Singleton
hubspot = HubSpotClient()
