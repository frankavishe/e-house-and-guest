"""`/auth/*` and `/me` endpoints (contracts/rest-api.md "Auth & profile")."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.accounts import deletion, service
from app.accounts.schemas import (
    MePatch,
    OtpRequestIn,
    OtpRequestOut,
    OtpVerifyIn,
    OtpVerifyOut,
    UserOut,
)
from app.core import ratelimit, security
from app.core.deps import CurrentUser, Session
from app.core.i18n import Locale, get_locale

router = APIRouter(tags=["auth"])

LocaleDep = Annotated[Locale, Depends(get_locale)]


@router.post(
    "/auth/otp/request", status_code=status.HTTP_202_ACCEPTED, response_model=OtpRequestOut
)
async def otp_request(
    body: OtpRequestIn, request: Request, session: Session, locale: LocaleDep
) -> OtpRequestOut:
    await ratelimit.hit_ip(session, ratelimit.OTP_PER_IP, request)
    expires_in = await service.request_otp(session, body.phone, locale)
    return OtpRequestOut(expires_in=expires_in)


@router.post("/auth/otp/verify", response_model=OtpVerifyOut)
async def otp_verify(
    body: OtpVerifyIn, session: Session, locale: LocaleDep, response: Response
) -> OtpVerifyOut:
    signed_in = await service.verify_otp(session, body.phone, body.code, locale)
    security.set_auth_cookies(response, signed_in.access_token, signed_in.refresh_token)
    return OtpVerifyOut(
        user=await service.user_out(session, signed_in.user), is_new=signed_in.is_new
    )


@router.post(
    "/auth/refresh",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={401: {"description": "Missing, expired, revoked or reused refresh token"}},
)
async def refresh(request: Request, session: Session) -> Response:
    signed_in = await service.rotate_refresh(session, request.cookies.get(security.REFRESH_COOKIE))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    security.set_auth_cookies(response, signed_in.access_token, signed_in.refresh_token)
    return response


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def logout(request: Request, session: Session, user: CurrentUser) -> Response:
    await service.logout(session, user, request.cookies.get(security.REFRESH_COOKIE))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    security.clear_auth_cookies(response)
    return response


@router.get("/me", response_model=UserOut, tags=["profile"])
async def get_me(session: Session, user: CurrentUser) -> UserOut:
    return await service.user_out(session, user)


@router.delete(
    "/me",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=Response,
    tags=["profile"],
    responses={
        202: {"description": "Account deleted; personal data anonymisation scheduled"},
        409: {"description": "`ACTIVE_BOOKINGS` or `PAYOUT_IN_PROGRESS`"},
    },
)
async def delete_me(session: Session, user: CurrentUser) -> Response:
    """Delete the account (FR-033). Bookings and payment records are kept, anonymised."""
    await deletion.request_deletion(session, user)
    response = Response(status_code=status.HTTP_202_ACCEPTED)
    security.clear_auth_cookies(response)
    return response


@router.patch("/me", response_model=UserOut, tags=["profile"])
async def patch_me(body: MePatch, session: Session, user: CurrentUser) -> UserOut:
    updated = await service.update_me(session, user, body)
    return await service.user_out(session, updated)
