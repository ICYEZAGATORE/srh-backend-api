"""
app/api/v1/endpoints/admin_auth.py
────────────────────────────────────
Admin-only authentication endpoints.

Routes
──────
POST /api/v1/admin/signup       — create a new admin account (existing admin only)
GET  /api/v1/admin/users        — list all users (admin only)
PATCH /api/v1/admin/users/{id}/deactivate  — deactivate a user account
PATCH /api/v1/admin/users/{id}/activate    — reactivate a user account
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import AdminSignupRequest, AuthResponse, UserPublicResponse
from app.services.auth_service import register_admin

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new admin account (admin only)",
)
def admin_signup(
    payload: AdminSignupRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),           # 🔒 only admins can call this
) -> AuthResponse:
    """
    Create a new system-admin account.
    Requires the caller to already be authenticated as an admin.

    Password policy for admins (stricter than users):
    - Minimum 10 characters
    - At least one uppercase letter
    - At least one digit
    - At least one special character
    """
    return register_admin(db, payload)


@router.get(
    "/users",
    response_model=list[UserPublicResponse],
    summary="List all registered users (admin only)",
)
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    skip: int = 0,
    limit: int = 50,
) -> list[UserPublicResponse]:
    """Paginated list of all platform users. Admin access required."""
    users = db.query(User).offset(skip).limit(limit).all()
    return [UserPublicResponse.model_validate(u) for u in users]


@router.patch(
    "/users/{user_id}/deactivate",
    response_model=UserPublicResponse,
    summary="Deactivate a user account (admin only)",
)
def deactivate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> UserPublicResponse:
    """Soft-deactivate a user. They cannot log in while deactivated."""
    if user_id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot deactivate their own account.",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    user.is_active = False
    user.refresh_token = None       # invalidate any active session
    db.commit()
    db.refresh(user)
    return UserPublicResponse.model_validate(user)


@router.patch(
    "/users/{user_id}/activate",
    response_model=UserPublicResponse,
    summary="Reactivate a user account (admin only)",
)
def activate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> UserPublicResponse:
    """Re-enable a previously deactivated user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    user.is_active = True
    db.commit()
    db.refresh(user)
    return UserPublicResponse.model_validate(user)
