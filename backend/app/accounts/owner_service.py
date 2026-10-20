"""Owner onboarding (US3, FR-004): profile, identity documents, verification submit and
payout methods. Admin review lives in `app/admin/moderation.py`."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import (
    OwnerKind,
    OwnerProfile,
    PaymentNetwork,
    PayoutKind,
    PayoutMethod,
    User,
    VerificationStatus,
)
from app.accounts.schemas import (
    OwnerProfileCreate,
    OwnerProfileOut,
    OwnerProfilePatch,
    PayoutMethodIn,
    PayoutMethodOut,
    UploadOut,
)
from app.core.db import uuid7
from app.core.errors import AppError, not_found
from app.core.security import decrypt, encrypt, mask_tail, normalize_phone
from app.integrations import get_storage

EDITABLE = {VerificationStatus.DRAFT, VerificationStatus.REJECTED}
DOCUMENT_TYPES = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}
DOCUMENT_MAX_BYTES = 10 * 1024 * 1024


def _masked(value: bytes | None) -> str | None:
    return mask_tail(decrypt(value)) if value else None


def document_prefix(profile: OwnerProfile) -> str:
    return f"owner-docs/{profile.id}/"


def profile_out(profile: OwnerProfile) -> OwnerProfileOut:
    return OwnerProfileOut(
        id=profile.id,
        kind=profile.kind.value,
        display_name=profile.display_name,
        business_name=profile.business_name,
        brela_reg_no=profile.brela_reg_no,
        nida_number_masked=_masked(profile.nida_number_enc),
        tin_masked=_masked(profile.tin_enc),
        documents=list(profile.documents),
        verification_status=profile.verification_status.value,
        rejection_reason=profile.rejection_reason,
        verified_at=profile.verified_at,
    )


def invalid_transition(status: VerificationStatus) -> AppError:
    return AppError("INVALID_TRANSITION", 409, {"status": status.value})


async def create_profile(
    session: AsyncSession, user: User, body: OwnerProfileCreate
) -> OwnerProfile:
    existing = await session.execute(select(OwnerProfile.id).where(OwnerProfile.user_id == user.id))
    if existing.first() is not None:
        raise AppError("CONFLICT", 409, message="You already have an owner profile.")
    business = body.kind == "business"
    profile = OwnerProfile(
        user_id=user.id,
        kind=OwnerKind(body.kind),
        display_name=body.display_name,
        nida_number_enc=encrypt(body.nida_number) if body.nida_number else None,
        business_name=body.business_name if business else None,
        brela_reg_no=body.brela_reg_no if business else None,
        tin_enc=encrypt(body.tin) if business and body.tin else None,
        documents=[],
        verification_status=VerificationStatus.DRAFT,
    )
    session.add(profile)
    await session.flush()
    return profile


async def patch_profile(
    session: AsyncSession, profile: OwnerProfile, patch: OwnerProfilePatch
) -> OwnerProfile:
    if profile.verification_status not in EDITABLE:
        raise invalid_transition(profile.verification_status)
    fields = patch.model_fields_set
    if "display_name" in fields and patch.display_name:
        profile.display_name = patch.display_name
    if "nida_number" in fields and patch.nida_number:
        profile.nida_number_enc = encrypt(patch.nida_number)
    if profile.kind == OwnerKind.BUSINESS:
        if "business_name" in fields and patch.business_name:
            profile.business_name = patch.business_name
        if "brela_reg_no" in fields and patch.brela_reg_no:
            profile.brela_reg_no = patch.brela_reg_no
        if "tin" in fields and patch.tin:
            profile.tin_enc = encrypt(patch.tin)
    if "documents" in fields and patch.documents is not None:
        prefix = document_prefix(profile)
        foreign = [key for key in patch.documents if not key.startswith(prefix)]
        if foreign:
            raise AppError("VALIDATION_ERROR", 422, {"documents": foreign})
        profile.documents = list(dict.fromkeys(patch.documents))
    await session.flush()
    return profile


def presign_document(profile: OwnerProfile, content_type: str) -> UploadOut:
    ext = DOCUMENT_TYPES.get(content_type)
    if ext is None:
        raise AppError("VALIDATION_ERROR", 422, {"content_type": sorted(DOCUMENT_TYPES)})
    put = get_storage().presign_put(
        key=f"{document_prefix(profile)}{uuid7()}.{ext}",
        content_type=content_type,
        max_bytes=DOCUMENT_MAX_BYTES,
        private=True,
    )
    return UploadOut(upload_url=put.url, storage_key=put.key, headers=put.headers)


async def submit_profile(session: AsyncSession, profile: OwnerProfile) -> OwnerProfile:
    """`draft | rejected → pending`; an admin then verifies or rejects it."""
    if profile.verification_status not in EDITABLE:
        raise invalid_transition(profile.verification_status)
    profile.verification_status = VerificationStatus.PENDING
    await session.flush()
    return profile


# --- payout methods -----------------------------------------------------------------------


def payout_method_out(method: PayoutMethod) -> PayoutMethodOut:
    return PayoutMethodOut(
        id=method.id,
        kind=method.kind.value,
        network=method.network.value if method.network else None,
        msisdn=method.msisdn,
        bank_name=method.bank_name,
        account_name=method.account_name,
        account_number_masked=_masked(method.account_number_enc),
        is_default=method.is_default,
    )


async def payout_methods(session: AsyncSession, profile: OwnerProfile) -> list[PayoutMethod]:
    rows = await session.execute(
        select(PayoutMethod)
        .where(PayoutMethod.owner_profile_id == profile.id)
        .order_by(PayoutMethod.created_at, PayoutMethod.id)
    )
    return list(rows.scalars())


async def _clear_default(session: AsyncSession, profile: OwnerProfile) -> None:
    await session.execute(
        update(PayoutMethod)
        .where(PayoutMethod.owner_profile_id == profile.id, PayoutMethod.is_default.is_(True))
        .values(is_default=False)
        .execution_options(synchronize_session="fetch")
    )


async def add_payout_method(
    session: AsyncSession, profile: OwnerProfile, body: PayoutMethodIn
) -> PayoutMethod:
    """The first method becomes the default; `is_default` moves it to the new one."""
    existing = await payout_methods(session, profile)
    default = body.is_default or not existing
    if default:
        await _clear_default(session, profile)
    mobile = body.kind == "mobile_money"
    method = PayoutMethod(
        owner_profile_id=profile.id,
        kind=PayoutKind(body.kind),
        network=PaymentNetwork(body.network) if mobile and body.network else None,
        msisdn=normalize_phone(body.msisdn) if mobile and body.msisdn else None,
        bank_name=None if mobile else body.bank_name,
        account_name=body.account_name,
        account_number_enc=None
        if mobile or not body.account_number
        else encrypt(body.account_number),
        is_default=default,
    )
    session.add(method)
    await session.flush()
    return method


async def delete_payout_method(
    session: AsyncSession, profile: OwnerProfile, method_id: uuid.UUID
) -> None:
    method = await session.get(PayoutMethod, method_id)
    if method is None or method.owner_profile_id != profile.id:
        raise not_found("payout_method")
    was_default = method.is_default
    await session.delete(method)
    await session.flush()
    if was_default:
        rest = await payout_methods(session, profile)
        if rest:
            rest[-1].is_default = True
            await session.flush()
