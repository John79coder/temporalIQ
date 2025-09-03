# app/auth/models/schemas.py
import re
from datetime import datetime
from typing import Optional, Dict, Any, List

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
        if not value or not value.strip():
            raise ValueError("Password cannot be blank or just spaces")

        # Check minimum length
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters long")

        # Check for at least one uppercase letter
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must contain at least one uppercase letter")

        # Check for at least one lowercase letter
        if not re.search(r"[a-z]", value):
            raise ValueError("Password must contain at least one lowercase letter")

        # Check for at least one digit
        if not re.search(r"\d", value):
            raise ValueError("Password must contain at least one number")

        # Check for at least one special character
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
    created_at: datetime
    updated_at: Optional[datetime] = None
    time_zone: Optional[str] = None
    # === NEW: Add 2FA status to user output ===
    two_factor_enabled: Optional[bool] = False


class TokenSchema(BaseModel):
    token: str


# === NEW SCHEMAS FOR APPLE SIGN-IN ===
class AppleSignIn(BaseModel):
    """Schema for Apple Sign In authentication"""
    id_token: Optional[str] = None
    authorization_code: Optional[str] = None
    user_info: Optional[Dict[str, Any]] = None

    @field_validator("id_token", "authorization_code")
    def validate_tokens(cls, v, info):
        # At least one must be provided
        if info.data.get('id_token') is None and info.data.get('authorization_code') is None:
            raise ValueError("Either id_token or authorization_code must be provided")
        return v


# === NEW SCHEMAS FOR 2FA ===
class TwoFactorSetup(BaseModel):
    """Schema for 2FA setup verification"""
    code: str = Field(..., min_length=6, max_length=6)
    secret: Optional[str] = None  # Optional, used for verification during setup

    @field_validator("code")
    def validate_code(cls, v):
        if not v.isdigit():
            raise ValueError("2FA code must contain only digits")
        return v


class TwoFactorVerify(BaseModel):
    """Schema for 2FA verification during login"""
    code: str = Field(..., min_length=6, max_length=10)  # 6 for TOTP, up to 10 for backup codes
    temp_token: str = Field(..., min_length=1)

    @field_validator("code")
    def validate_code(cls, v):
        # Allow alphanumeric for backup codes (they might have dashes)
        cleaned = v.replace("-", "").replace(" ", "")
        if not cleaned.isalnum():
            raise ValueError("Invalid code format")
        return cleaned  # Return cleaned version


class TwoFactorBackupCodes(BaseModel):
    """Schema for backup codes response"""
    backup_codes: List[str]
    generated_at: datetime


class TwoFactorStatus(BaseModel):
    """Schema for 2FA status response"""
    enabled: bool
    backup_codes_count: int = 0
    last_used: Optional[datetime] = None