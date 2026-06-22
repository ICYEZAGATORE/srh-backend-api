"""
app/api/v1/endpoints/auth.py
──────────────────────────────
Public and user-facing authentication endpoints.

Routes
──────
POST /api/v1/auth/signup        — register a new user account
POST /api/v1/auth/login         — login (users and admins share this endpoint)
POST /api/v1/auth/refresh       — exchange refresh token for new tokens
POST /api/v1/auth/logout        — invalidate refresh token (requires auth)
GET  /api/v1/auth/me            — get current user profile (requires auth)
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserPublicResponse,
    UserSignupRequest,
)
from app.services.auth_service import (
    login,
    logout,
    refresh_tokens,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
def signup(payload: UserSignupRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """
    Register a new platform user (teenager or PWD).

    - Returns access + refresh tokens immediately after signup.
    - Password must be ≥ 8 chars, contain at least one uppercase and one digit.
    - `disability_type` is optional (defaults to "none").
    - `preferred_language` accepts "en" or "rw" (Kinyarwanda).
    """
    return register_user(db, payload)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Login — users and admins",
)
def login_endpoint(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """
    Authenticate with email + password.
    Works for both regular users and system admins.
    The `role` field in the response distinguishes them.
    """
    return login(db, payload)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
)
def refresh_endpoint(
    payload: RefreshRequest, db: Session = Depends(get_db)
) -> TokenResponse:
    """
    Exchange a valid refresh token for a fresh access token + new refresh token.
    Refresh tokens are rotated on every use (prevents replay attacks).
    """
    return refresh_tokens(db, payload.refresh_token)


@router.post(
    "/logout",
    summary="Logout (invalidates refresh token)",
)
def logout_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Invalidate the current user's refresh token.
    The access token will expire naturally after its TTL.
    """
    return logout(db, current_user)


@router.get(
    "/me",
    response_model=UserPublicResponse,
    summary="Get current user profile",
)
def get_me(current_user: User = Depends(get_current_user)) -> UserPublicResponse:
    """Return the profile of the currently authenticated user."""
    return UserPublicResponse.model_validate(current_user)
