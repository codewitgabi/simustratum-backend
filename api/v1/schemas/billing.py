from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SelectPlanRequest(BaseModel):
    plan: Literal["free"]


class CheckoutRequest(BaseModel):
    plan: Literal["pro"]
    currency: Literal["NGN", "USD"]


class PortalRequest(BaseModel):
    return_url: str


class BillingStatusResponse(BaseModel):
    plan: str
    sessions_used: int
    sessions_limit: int | None
    billing_period_end: datetime | None
    cancel_at_period_end: bool
