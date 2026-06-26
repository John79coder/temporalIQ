from pydantic import BaseModel, ConfigDict


class UserTwoFactorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    enabled: bool


class TwoFactorSetupResponse(BaseModel):
    qr_code: str
    secret: str
    manual_entry_key: str
    issuer: str


class TwoFactorVerifyRequest(BaseModel):
    code: str


class TwoFactorVerifyResponse(BaseModel):
    backup_codes: list[str]


class TwoFactorStatusResponse(BaseModel):
    two_factor_enabled: bool
    codes_remaining: int


class BackupCodesResponse(BaseModel):
    backup_codes: list[str]