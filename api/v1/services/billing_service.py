import asyncio
import uuid
from datetime import date, datetime, timezone

import stripe
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.models.user import User
from api.v1.utils.config import config
from api.v1.utils.logger import get_logger

logger = get_logger("billing")

FREE_SESSION_LIMIT = 15


def _init_stripe() -> None:
    stripe.api_key = config.STRIPE_SECRET_KEY


def _reset_usage_if_stale(user: User) -> bool:
    today = date.today()
    current_month_start = today.replace(day=1)
    if user.billing_month is None or user.billing_month < current_month_start:
        user.sessions_used_this_month = 0
        user.billing_month = current_month_start
        return True
    return False


async def check_session_limit(user: User, db: AsyncSession) -> None:
    """Raise 402 if a free/unselected-plan user has hit the monthly cap."""
    if user.plan == "pro":
        return
    if _reset_usage_if_stale(user):
        await db.commit()
    if user.sessions_used_this_month >= FREE_SESSION_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="session_limit_reached",
        )


async def increment_session_usage(user: User, db: AsyncSession) -> None:
    if user.plan != "pro":
        user.sessions_used_this_month = (user.sessions_used_this_month or 0) + 1
        await db.commit()


async def set_free_plan(user: User, db: AsyncSession) -> None:
    if user.plan is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has a plan",
        )
    user.plan = "free"
    await db.commit()


async def create_checkout_session(user: User, currency: str, db: AsyncSession) -> str:
    _init_stripe()
    if user.plan == "pro" and user.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has an active Pro subscription",
        )

    customer_id = await _get_or_create_stripe_customer(user, db)

    if not config.FRONTEND_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="FRONTEND_URL is not configured on the server",
        )

    price_id = config.STRIPE_PRICE_ID_NGN if currency == "NGN" else config.STRIPE_PRICE_ID_USD
    frontend_url = config.FRONTEND_URL.rstrip("/")

    checkout = await asyncio.to_thread(
        stripe.checkout.Session.create,
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{frontend_url}/plans/success",
        cancel_url=f"{frontend_url}/plans",
        metadata={"user_id": str(user.id)},
    )
    return checkout.url


async def create_portal_session(user: User, return_url: str) -> str:
    _init_stripe()
    if not user.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No billing account found — you are on the Free plan",
        )
    portal = await asyncio.to_thread(
        stripe.billing_portal.Session.create,
        customer=user.stripe_customer_id,
        return_url=return_url,
    )
    return portal.url


def get_billing_status(user: User) -> dict:
    _reset_usage_if_stale(user)
    return {
        "plan": user.plan or "free",
        "sessions_used": user.sessions_used_this_month or 0,
        "sessions_limit": FREE_SESSION_LIMIT if user.plan != "pro" else None,
        "billing_period_end": (
            user.billing_period_end.isoformat() if user.billing_period_end else None
        ),
        "cancel_at_period_end": user.cancel_at_period_end or False,
    }


async def handle_webhook(payload: bytes, sig_header: str, db: AsyncSession) -> None:
    _init_stripe()
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, config.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )

    try:
        await _dispatch_event(event, db)
    except Exception:
        logger.exception(
            "Webhook event processing failed",
            extra={"event_type": event.type},
        )


async def _dispatch_event(event: stripe.Event, db: AsyncSession) -> None:
    event_type: str = event.type
    data = event.data.object

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data, db)

    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(data, db)

    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data, db)

    elif event_type == "invoice.payment_failed":
        logger.warning(
            "Invoice payment failed",
            extra={"invoice_id": getattr(data, "id", None), "customer": getattr(data, "customer", None)},
        )


async def _handle_checkout_completed(data: stripe.checkout.Session, db: AsyncSession) -> None:
    metadata = getattr(data, "metadata", None) or {}
    user_id_str = metadata.get("user_id") if isinstance(metadata, dict) else getattr(metadata, "user_id", None)
    if not user_id_str:
        return

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        logger.warning("checkout.session.completed has invalid user_id in metadata", extra={"user_id": user_id_str})
        return

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return

    subscription_id: str | None = getattr(data, "subscription", None)
    customer_id: str | None = getattr(data, "customer", None)

    raw_currency = (getattr(data, "currency", None) or "usd").upper()
    billing_currency = raw_currency if raw_currency in ("NGN", "USD") else "USD"

    period_end: datetime | None = None
    if subscription_id:
        sub = await asyncio.to_thread(stripe.Subscription.retrieve, subscription_id)
        ts = getattr(sub, "current_period_end", None)
        if ts:
            period_end = datetime.fromtimestamp(ts, tz=timezone.utc)

    user.plan = "pro"
    user.stripe_customer_id = customer_id
    user.stripe_subscription_id = subscription_id
    user.billing_currency = billing_currency
    user.billing_period_end = period_end
    user.cancel_at_period_end = False
    await db.commit()


async def _handle_subscription_updated(data: stripe.Subscription, db: AsyncSession) -> None:
    subscription_id: str = getattr(data, "id", "")
    result = await db.execute(
        select(User).where(User.stripe_subscription_id == subscription_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return

    ts = getattr(data, "current_period_end", None)
    user.billing_period_end = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
    user.cancel_at_period_end = getattr(data, "cancel_at_period_end", False)
    if getattr(data, "status", None) == "active":
        user.plan = "pro"
    await db.commit()


async def _handle_subscription_deleted(data: stripe.Subscription, db: AsyncSession) -> None:
    subscription_id: str = getattr(data, "id", "")
    result = await db.execute(
        select(User).where(User.stripe_subscription_id == subscription_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return

    user.plan = "free"
    user.stripe_subscription_id = None
    user.billing_period_end = None
    user.cancel_at_period_end = False
    user.sessions_used_this_month = 0
    user.billing_month = None
    await db.commit()


async def _get_or_create_stripe_customer(user: User, db: AsyncSession) -> str:
    if user.stripe_customer_id:
        return user.stripe_customer_id

    customer = await asyncio.to_thread(
        stripe.Customer.create,
        email=user.email,
        name=user.full_name,
        metadata={"user_id": str(user.id)},
    )
    user.stripe_customer_id = customer.id
    await db.commit()
    return customer.id
