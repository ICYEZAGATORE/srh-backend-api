"""
app/services/auth_service.py
─────────────────────────────
Business logic for signup, login, token refresh, and logout.
Shared by both user and admin endpoints.
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserRole
from app.schemas.auth import (
    AdminSignupRequest,
    AuthResponse,
    LoginRequest,
    TokenResponse,
    UserPublicResponse,
    UserSignupRequest,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _build_token_response(user: User) -> TokenResponse:
    access = create_access_token(str(user.id), user.role.value)
    refresh = create_refresh_token(str(user.id), user.role.value)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def _save_refresh_token(db: Session, user: User, refresh_token: str) -> None:
    user.refresh_token = refresh_token
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)


# ── User signup ───────────────────────────────────────────────────────────────

def register_user(db: Session, payload: UserSignupRequest) -> AuthResponse:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        age=payload.age,
        preferred_language=payload.preferred_language,
        disability_type=payload.disability_type,
        role=UserRole.USER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    tokens = _build_token_response(user)
    _save_refresh_token(db, user, tokens.refresh_token)

    return AuthResponse(tokens=tokens, user=UserPublicResponse.model_validate(user))


# ── Admin signup (restricted) ─────────────────────────────────────────────────

def register_admin(db: Session, payload: AdminSignupRequest) -> AuthResponse:
    """
    Creates a new admin account.
    Must only be called from an endpoint protected by `require_admin` dependency.
    """
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.ADMIN,
        is_verified=True,       # admins are pre-verified
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    tokens = _build_token_response(user)
    _save_refresh_token(db, user, tokens.refresh_token)

    return AuthResponse(tokens=tokens, user=UserPublicResponse.model_validate(user))


# ── Login (shared for users and admins) ──────────────────────────────────────

def login(db: Session, payload: LoginRequest) -> AuthResponse:
    user = db.query(User).filter(User.email == payload.email).first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact support.",
        )

    tokens = _build_token_response(user)
    _save_refresh_token(db, user, tokens.refresh_token)

    return AuthResponse(tokens=tokens, user=UserPublicResponse.model_validate(user))


# ── Token refresh ────────────────────────────────────────────────────────────

def refresh_tokens(db: Session, refresh_token: str) -> TokenResponse:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise credentials_error
        user_id: str = payload.get("sub")
    except Exception:
        raise credentials_error

    user = db.query(User).filter(User.id == user_id).first()

    if not user or user.refresh_token != refresh_token:
        raise credentials_error
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated.")

    # Rotate the refresh token on every use (prevents replay)
    tokens = _build_token_response(user)
    _save_refresh_token(db, user, tokens.refresh_token)

    return tokens


# ── Logout ────────────────────────────────────────────────────────────────────

def logout(db: Session, user: User) -> dict:
    user.refresh_token = None
    db.commit()
    return {"message": "Logged out successfully."}
