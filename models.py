"""Pydantic models for Lead Distribution Portal."""
from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
import uuid


class BudgetRange(str, Enum):
    UNDER_10K = "Under $10k"
    BETWEEN_10K_50K = "$10k-$50k"
    OVER_50K = "Greater than $50k"


class LocalStatus(str, Enum):
    RECEIVED = "received"
    VALIDATED = "validated"
    FAILED = "failed"


class HubSpotStatus(str, Enum):
    PENDING = "pending"
    SYNCING = "syncing"
    SYNCED = "synced"
    FAILED = "failed"
    SKIPPED = "skipped"


# Disposable / non-corporate email domains we reject
BLOCKED_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "aol.com", "icloud.com", "mail.com", "protonmail.com",
}


class LeadInput(BaseModel):
    """Incoming form submission payload."""
    first_name: str = Field(..., min_length=1, max_length=80)
    last_name: str = Field(..., min_length=1, max_length=80)
    email: EmailStr
    company: str = Field(..., min_length=1, max_length=120)
    budget: BudgetRange

    @field_validator("email")
    @classmethod
    def must_be_corporate(cls, v: str) -> str:
        domain = v.split("@")[-1].lower()
        if domain in BLOCKED_DOMAINS:
            raise ValueError(
                f"Please use a corporate email address (not {domain})."
            )
        return v.lower()


class SyncAttempt(BaseModel):
    """One HubSpot sync attempt for audit/debug log."""
    at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    attempt: int = 1
    success: bool = False
    contact_id: Optional[str] = None
    error: Optional[str] = None
    mode: str = "mock"  # "mock" or "live"


class Lead(BaseModel):
    """Lead record stored locally."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    first_name: str
    last_name: str
    email: str
    company: str
    budget: BudgetRange
    estimated_value: float = 0.0
    local_status: LocalStatus = LocalStatus.RECEIVED
    hubspot_status: HubSpotStatus = HubSpotStatus.PENDING
    hubspot_contact_id: Optional[str] = None
    hubspot_error: Optional[str] = None
    sync_attempts: List[SyncAttempt] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# Map budget range to midpoint dollar value for pipeline math
BUDGET_TO_VALUE = {
    BudgetRange.UNDER_10K: 5_000.0,
    BudgetRange.BETWEEN_10K_50K: 30_000.0,
    BudgetRange.OVER_50K: 75_000.0,
}
