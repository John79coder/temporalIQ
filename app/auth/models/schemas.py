import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator, Field, model_serializer, ConfigDict

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


class UserCreate(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    def validate_password(cls, value: str) -> str:
        """Validate password strength according to security best practices."""
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if len(value) > 64:
            raise ValueError("Password must not exceed 64 characters")

        # Check for required character types
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", value):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"[0-9]", value):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]", value):
            raise ValueError("Password must contain at least one special character")

        # Basic check for common weak passwords
        if "password" in value.lower():
            raise ValueError("Password cannot contain the word 'password'")

        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)

    @field_validator("password")
    def strip_and_check_not_blank(cls, v):
        if not v.strip():
            raise ValueError("Password cannot be blank or just spaces")
        return v


class UserOut(BaseOutModel):
    id: int
    email: EmailStr
    is_verified: bool
    two_factor_enabled: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    time_zone: Optional[str] = None


class TokenSchema(BaseModel):
    token: str


class AppleSignIn(BaseModel):
    id_token: str
