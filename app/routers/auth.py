"""Auth router — /auth prefix."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.settings import get_settings
from app.user_auth import (
    authenticate_user,
    create_access_token,
    create_app_user,
    list_app_users,
    reset_app_user_password,
    require_admin_user,
    require_authenticated_user,
    serialize_app_user,
    ROLE_ADMIN,
    ROLE_VIEWER,
)
import structlog

log = structlog.get_logger()
settings = get_settings()

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=256)
    display_name: Optional[str] = Field(None, max_length=128)
    role: str = Field(ROLE_VIEWER, description="admin or viewer")


class ResetUserPasswordRequest(BaseModel):
    password: str = Field(..., min_length=8, max_length=256)


@router.post("/login", summary="Sign in with username and password")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    from app.user_auth import check_login_rate_limit, record_login_failure, clear_login_failures

    client_ip = request.client.host if request.client else "unknown"
    if not check_login_rate_limit(db, client_ip):
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again later.")

    user = authenticate_user(db, body.username, body.password)
    if not user:
        record_login_failure(db, client_ip)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    clear_login_failures(db, client_ip)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    if settings.is_production and not settings.jwt_configured:
        log.error("login_blocked", reason="jwt_secret_missing")
        raise HTTPException(
            status_code=503,
            detail="Sign-in is not configured. Ask your administrator to set JWT_SECRET in App Service settings.",
        )

    try:
        token = create_access_token(user_id=user.id, username=user.username, role=user.role)
    except RuntimeError as exc:
        log.error("login_blocked", reason=str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name or user.username,
            "role": user.role,
        },
    }


@router.get("/me", summary="Current signed-in user")
def auth_me(request: Request):
    user = require_authenticated_user(request)
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user.get("display_name") or user["username"],
        "role": user["role"],
        "is_admin": user.get("role") == ROLE_ADMIN,
    }


@router.get("/users", summary="List application users (admin only)")
def list_users(request: Request, db: Session = Depends(get_db)):
    require_admin_user(request)
    return list_app_users(db)


@router.post("/users", summary="Create an application user (admin only)")
def create_user(request: Request, body: CreateUserRequest, db: Session = Depends(get_db)):
    require_admin_user(request)
    try:
        user = create_app_user(
            db,
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            role=body.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "user": serialize_app_user(user)}


@router.patch("/users/{user_id}/password", summary="Reset a user's password (admin only)")
def reset_user_password(
    request: Request,
    user_id: str = Path(...),
    body: ResetUserPasswordRequest = Body(...),
    db: Session = Depends(get_db),
):
    require_admin_user(request)
    try:
        user = reset_app_user_password(db, user_id, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "user": serialize_app_user(user)}
