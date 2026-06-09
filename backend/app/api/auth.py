from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, create_access_token, verify_credentials
from app.core.config import get_settings
from app.core.database import get_db
from app.schemas import AuthBootstrapResponse, LoginRequest, LoginResponse, LogoutResponse
from app.services.app_settings import get_app_display_name

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.get("/bootstrap", response_model=AuthBootstrapResponse)
def auth_bootstrap(db: Session = Depends(get_db)) -> AuthBootstrapResponse:
    return AuthBootstrapResponse(
        auth_enabled=settings.auth_enabled,
        app_display_name=get_app_display_name(db),
    )


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    if not settings.auth_enabled:
        return LoginResponse(
            username=settings.auth_username,
            app_display_name=get_app_display_name(db),
        )

    if not verify_credentials(payload.username, payload.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    token = create_access_token(payload.username)
    max_age = settings.auth_token_expire_hours * 3600
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=max_age,
        secure=settings.auth_cookie_secure,
    )
    return LoginResponse(
        username=payload.username,
        access_token=token,
        app_display_name=get_app_display_name(db),
    )


@router.get("/me", response_model=LoginResponse)
def auth_me(
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> LoginResponse:
    return LoginResponse(
        username=user if user != "anonymous" else settings.auth_username,
        app_display_name=get_app_display_name(db),
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(response: Response) -> LogoutResponse:
    response.delete_cookie(key=settings.auth_cookie_name)
    return LogoutResponse(status="ok")
