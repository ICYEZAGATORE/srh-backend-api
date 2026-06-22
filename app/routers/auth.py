"""
auth.py — POST /api/v1/auth/signup  |  POST /api/v1/auth/signin
JWT-based authentication. Passwords hashed with bcrypt.
User data stored in PostgreSQL via SQLAlchemy.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.models.user import User


router = APIRouter(prefix="/auth")

# ── Security helpers ──────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/signin", auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(payload, settings.APP_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Returns the current user if a valid token is provided, else None."""
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, settings.APP_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        return db.query(User).filter(User.id == int(user_id)).first()
    except JWTError:
        return None


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Returns the current user. Raises 401 if token is missing or invalid."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(
            token, settings.APP_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user


# ── Request / Response schemas ────────────────────────────────────────────────

class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Minimum 8 characters.")
    age_group: str = Field(
        description="13-15 | 16-19 | 20+ | prefer_not_to_say",
        examples=["16-19"],
    )
    disability_type: Optional[str] = Field(
        default=None,
        description="visual | hearing | physical | cognitive | none | prefer_not_to_say",
    )
    language_preference: str = Field(default="en", description="en | rw")


class SignInResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    language_preference: str


class UserProfileResponse(BaseModel):
    user_id: int
    email: str
    age_group: str
    language_preference: str
    disability_type: Optional[str]
    created_at: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/signup",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Create a new account. Email and password required. "
        "Age group and disability type are optional but improve platform personalisation."
    ),
)
async def signup(body: SignUpRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        age_group=body.age_group,
        disability_type=body.disability_type or "none",
        language_preference=body.language_preference,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Account created successfully.", "user_id": user.id}


@router.post(
    "/signin",
    response_model=SignInResponse,
    summary="Sign in and get access token",
    description="Authenticate with email and password. Returns a JWT bearer token.",
)
async def signin(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": str(user.id)})
    return SignInResponse(
        access_token=token,
        user_id=user.id,
        language_preference=user.language_preference,
    )


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Get current user profile",
)
async def get_profile(current_user: User = Depends(get_current_user)):
    return UserProfileResponse(
        user_id=current_user.id,
        email=current_user.email,
        age_group=current_user.age_group,
        language_preference=current_user.language_preference,
        disability_type=current_user.disability_type,
        created_at=current_user.created_at.isoformat(),
    )