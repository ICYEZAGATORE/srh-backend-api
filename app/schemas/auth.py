"""
app/schemas/auth.py
───────────────────
Pydantic v2 schemas for request/response validation.
Covers both user and admin auth endpoints.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import DisabilityType, UserRole


# ─── Signup ────────────────────────────────────────────────────────────────────

class UserSignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(None, max_length=150)
    age: int | None = Field(None, ge=10, le=100)
    preferred_language: str = Field("en", pattern="^(en|rw)$")
    disability_type: DisabilityType = DisabilityType.NONE

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class AdminSignupRequest(BaseModel):
    """Used by a super-admin to create additional admin accounts."""
    email: EmailStr
    password: str = Field(..., min_length=10, max_length=128)
    full_name: str = Field(..., max_length=150)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        specials = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in specials for c in v):
            raise ValueError("Password must contain at least one special character")
        return v


# ─── Login ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ─── Token responses ───────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int                 # seconds until access token expires


class RefreshRequest(BaseModel):
    refresh_token: str


# ─── User info responses ───────────────────────────────────────────────────────

class UserPublicResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str | None
    role: UserRole
    is_active: bool
    is_verified: bool
    preferred_language: str
    disability_type: DisabilityType
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    """Combines token + user info in a single sign-in response."""
    tokens: TokenResponse
    user: UserPublicResponse
