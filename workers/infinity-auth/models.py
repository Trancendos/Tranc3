"""
Infinity Auth — Pydantic Models
================================
All request/response models used by the infinity-auth worker.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=100)
    role: str = Field(default="user")  # Phase 22.5: role for Infinity Gate routing


class UserLogin(BaseModel):
    username: str
    password: str
    totp_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    username: str
    # Phase 22.5: Tier-aware claims
    role: str = "user"
    tier: int = 0
    infinity_role: str = "user"


class RefreshRequest(BaseModel):
    refresh_token: str


class TOTPSetupResponse(BaseModel):
    secret: str
    qr_code_url: str
    backup_codes: list[str]


class UserProfile(BaseModel):
    user_id: str
    username: str
    email: str
    display_name: str
    mfa_enabled: bool
    created_at: str
    last_login: str | None = None
    # Phase 22.5: Extended profile
    role: str = "user"
    tier: int = 0
    infinity_role: str = "user"


class TokenRequest(BaseModel):
    grant_type: str
    code: str = ""
    redirect_uri: str = ""
    client_id: str = ""
    client_secret: str = ""
    code_verifier: str = ""
    refresh_token: str = ""
