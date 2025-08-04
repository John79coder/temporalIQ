from pydantic import BaseModel, model_serializer, Field, ConfigDict
from datetime import datetime
from typing import Optional
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

class SubscriptionCreate(BaseModel):
    user_id: int = Field(ge=1)
    plan_type: str = Field(default='free', pattern=r'^(free|basic|premium)$')
    stripe_id: Optional[str] = None

class SubscriptionUpdate(BaseModel):
    plan_type: Optional[str] = None
    status: Optional[str] = None
    end_date: Optional[datetime] = None
    stripe_id: Optional[str] = None

class SubscriptionOut(BaseOutModel):
    id: int
    user_id: int
    plan_type: str
    status: str
    start_date: datetime
    end_date: Optional[datetime]
    stripe_id: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]