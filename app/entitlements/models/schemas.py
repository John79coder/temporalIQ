# app/entitlements/models/schemas.py
from datetime import datetime
from typing import Optional, Dict, List
from pydantic import BaseModel, Field, ConfigDict, model_serializer
from app.utils.time_zone import TimeZone


class BaseOutModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @model_serializer(mode='wrap')
    def serialize_model(self, handler) -> dict:
        data = handler(self)
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = TimeZone.serialize_datetime(value)
        return data


class TierLimits(BaseModel):
    ai_generations: int
    calendar_writes: int
    calendars: int
    notion_databases: int
    auto_reschedule: Optional[str]
    priority_queue: bool = False
    webhook_access: bool = False
    api_access: bool = False


class UsageStatus(BaseOutModel):
    tier: str
    status: str
    trial_ends_at: Optional[datetime]
    usage: Dict[str, Dict[str, int]]  # {"ai_generations": {"used": 50, "limit": 100}}
    capabilities: List[str]
    upgrade_options: List[str]


class QuotaCheckResult(BaseModel):
    allowed: bool
    remaining: int
    limit: int
    reset_date: datetime
    upgrade_options: Optional[List[str]] = None
    credit_pack_available: bool = False


class CreditPackPurchase(BaseModel):
    credit_type: str = Field(..., pattern="^(ai_generations|calendar_writes)$")
    amount: int = Field(..., ge=100, le=10000)


class UpgradeRequest(BaseModel):
    target_tier: str = Field(..., pattern="^(free|starter|pro|business)$")
    annual_billing: bool = False
    promo_code: Optional[str] = None