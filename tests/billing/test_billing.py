"""Integration tests for billing endpoints and plan enforcement."""

import asyncio as real_asyncio
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
import stripe
from httpx import AsyncClient
from sqlalchemy import select

import api.v1.services.billing_service as billing_mod
from tests.utils import auth_header, registered_user_headers, sample_panelists


# ─────────────────────────── DB helpers ──────────────────────────────────────


async def _set_user_billing(user_id: str, **fields) -> None:
    import api.database as database_module
    from api.v1.models.user import User

    async with database_module.AsyncSessionLocal() as db:
        user = await db.get(User, uuid.UUID(user_id))
        for k, v in fields.items():
            setattr(user, k, v)
        await db.commit()


async def _get_user(user_id: str):
    import api.database as database_module
    from api.v1.models.user import User

    async with database_module.AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        return result.scalar_one()


# ─────────────────────────── HTTP helpers ────────────────────────────────────


async def _register(client: AsyncClient) -> tuple[str, dict]:
    """Registers a fresh user and returns (user_id, auth_headers)."""
    email = f"billing-{uuid.uuid4().hex[:10]}@test.com"
    res = await client.post(
        "/api/v1/auth/register",
        json={"full_name": "Billing User", "email": email, "password": "strongpass123"},
    )
    assert res.status_code == 201, res.text
    data = res.json()["data"]
    user_id = str(data["user"]["id"])
    headers = auth_header(data["tokens"]["access_token"])
    return user_id, headers


async def _create_session(client: AsyncClient, headers: dict, panelists: list | None = None) -> dict:
    res = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={
            "scenario": "project_defense",
            "topic": "Billing test session",
            "panelists": panelists if panelists is not None else [sample_panelists()[0]],
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


# ─────────────────────────── Stripe stubs ────────────────────────────────────


class _FakeStripeObject:
    """Lightweight stand-in for stripe.StripeObject — supports getattr access."""

    def __init__(self, **fields):
        for k, v in fields.items():
            setattr(self, k, v)


class _FakeEvent:
    def __init__(self, event_type: str, data_object):
        self.type = event_type
        self.data = SimpleNamespace(object=data_object)


@pytest.fixture
def stub_stripe(monkeypatch):
    """
    Replaces asyncio.to_thread inside billing_service with a fake that returns
    pre-configured Stripe objects, and patches stripe.Webhook.construct_event
    with a sentinel that raises NotImplementedError by default (override per-test
    with _fake_webhook_event).
    """
    CUSTOMER_ID = "cus_test_123456"
    SUBSCRIPTION_ID = "sub_test_789"
    CHECKOUT_URL = "https://checkout.stripe.com/c/pay/cs_test_fake"
    PORTAL_URL = "https://billing.stripe.com/session/test_fake"
    PERIOD_END_TS = 2_000_000_000  # 2033-05-18

    class FakeAsyncio:
        gather = real_asyncio.gather

        @staticmethod
        async def to_thread(func, *args, **kwargs):
            name = getattr(func, "__name__", "")
            if name == "retrieve":
                return _FakeStripeObject(current_period_end=PERIOD_END_TS)
            if name == "create":
                if "line_items" in kwargs:
                    return _FakeStripeObject(url=CHECKOUT_URL)
                if "return_url" in kwargs:
                    return _FakeStripeObject(url=PORTAL_URL)
                return _FakeStripeObject(id=CUSTOMER_ID)
            raise ValueError(f"Unexpected stripe call in test: {name!r} args={args} kwargs={kwargs}")

    monkeypatch.setattr(billing_mod, "asyncio", FakeAsyncio)

    return {
        "customer_id": CUSTOMER_ID,
        "subscription_id": SUBSCRIPTION_ID,
        "checkout_url": CHECKOUT_URL,
        "portal_url": PORTAL_URL,
        "period_end_ts": PERIOD_END_TS,
    }


def _fake_webhook_event(monkeypatch, event_type: str, data_object) -> _FakeEvent:
    """Patches stripe.Webhook.construct_event to return a fake event for one test."""
    event = _FakeEvent(event_type, data_object)
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a: event)
    return event


# ══════════════════════════ GET /billing/status ═══════════════════════════════


@pytest.mark.asyncio
async def test_billing_status_new_user_shows_free_plan(client):
    headers = await registered_user_headers(client)
    res = await client.get("/api/v1/billing/status", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["plan"] == "free"
    assert data["sessions_limit"] == 15
    assert data["sessions_used"] == 0
    assert data["billing_period_end"] is None
    assert data["cancel_at_period_end"] is False


@pytest.mark.asyncio
async def test_billing_status_pro_user_has_no_session_limit(client):
    user_id, headers = await _register(client)
    await _set_user_billing(
        user_id,
        plan="pro",
        stripe_subscription_id="sub_existing",
        billing_period_end=datetime(2026, 8, 1, tzinfo=timezone.utc),
        cancel_at_period_end=False,
    )
    res = await client.get("/api/v1/billing/status", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["plan"] == "pro"
    assert data["sessions_limit"] is None
    assert data["billing_period_end"] is not None


@pytest.mark.asyncio
async def test_billing_status_requires_auth(client):
    res = await client.get("/api/v1/billing/status")
    assert res.status_code in (401, 403)


# ══════════════════════════ POST /billing/plan ════════════════════════════════


@pytest.mark.asyncio
async def test_select_free_plan_sets_plan_on_new_user(client):
    user_id, headers = await _register(client)
    res = await client.post("/api/v1/billing/plan", headers=headers, json={"plan": "free"})
    assert res.status_code == 200
    user = await _get_user(user_id)
    assert user.plan == "free"


@pytest.mark.asyncio
async def test_select_free_plan_returns_409_if_plan_already_set(client):
    user_id, headers = await _register(client)
    await _set_user_billing(user_id, plan="free")
    res = await client.post("/api/v1/billing/plan", headers=headers, json={"plan": "free"})
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_select_free_plan_requires_auth(client):
    res = await client.post("/api/v1/billing/plan", json={"plan": "free"})
    assert res.status_code in (401, 403)


# ══════════════════════════ POST /billing/checkout ════════════════════════════


@pytest.mark.asyncio
async def test_checkout_returns_stripe_checkout_url(client, stub_stripe):
    headers = await registered_user_headers(client)
    res = await client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plan": "pro", "currency": "NGN"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["checkout_url"] == stub_stripe["checkout_url"]


@pytest.mark.asyncio
async def test_checkout_ngn_and_usd_both_accepted(client, stub_stripe):
    for currency in ("NGN", "USD"):
        _, headers = await _register(client)
        res = await client.post(
            "/api/v1/billing/checkout",
            headers=headers,
            json={"plan": "pro", "currency": currency},
        )
        assert res.status_code == 200, f"currency={currency}: {res.text}"


@pytest.mark.asyncio
async def test_checkout_returns_409_if_already_subscribed(client, stub_stripe):
    user_id, headers = await _register(client)
    await _set_user_billing(
        user_id,
        plan="pro",
        stripe_subscription_id="sub_existing",
        stripe_customer_id="cus_existing",
    )
    res = await client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plan": "pro", "currency": "USD"},
    )
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_checkout_returns_500_if_frontend_url_missing(client, monkeypatch, stub_stripe):
    from api.v1.utils.config import config as real_config

    fake_config = SimpleNamespace(
        FRONTEND_URL="",
        STRIPE_SECRET_KEY=real_config.STRIPE_SECRET_KEY,
        STRIPE_WEBHOOK_SECRET=real_config.STRIPE_WEBHOOK_SECRET,
        STRIPE_PRICE_ID_NGN=real_config.STRIPE_PRICE_ID_NGN,
        STRIPE_PRICE_ID_USD=real_config.STRIPE_PRICE_ID_USD,
    )
    monkeypatch.setattr(billing_mod, "config", fake_config)

    headers = await registered_user_headers(client)
    res = await client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plan": "pro", "currency": "NGN"},
    )
    assert res.status_code == 500


@pytest.mark.asyncio
async def test_checkout_requires_auth(client):
    res = await client.post("/api/v1/billing/checkout", json={"plan": "pro", "currency": "USD"})
    assert res.status_code in (401, 403)


# ══════════════════════════ POST /billing/portal ══════════════════════════════


@pytest.mark.asyncio
async def test_portal_returns_portal_url_for_pro_user(client, stub_stripe):
    user_id, headers = await _register(client)
    await _set_user_billing(user_id, plan="pro", stripe_customer_id=stub_stripe["customer_id"])

    res = await client.post(
        "/api/v1/billing/portal",
        headers=headers,
        json={"return_url": "https://simustratum.com/settings"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["portal_url"] == stub_stripe["portal_url"]


@pytest.mark.asyncio
async def test_portal_returns_403_for_user_without_stripe_customer(client):
    headers = await registered_user_headers(client)
    res = await client.post(
        "/api/v1/billing/portal",
        headers=headers,
        json={"return_url": "https://simustratum.com/settings"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_portal_requires_auth(client):
    res = await client.post("/api/v1/billing/portal", json={"return_url": "https://x.com"})
    assert res.status_code in (401, 403)


# ══════════════════════════ POST /billing/webhook ═════════════════════════════


@pytest.mark.asyncio
async def test_webhook_checkout_completed_upgrades_user_to_pro(client, monkeypatch, stub_stripe):
    user_id, _ = await _register(client)

    data_obj = _FakeStripeObject(
        metadata={"user_id": user_id},
        subscription=stub_stripe["subscription_id"],
        customer=stub_stripe["customer_id"],
        currency="usd",
    )
    _fake_webhook_event(monkeypatch, "checkout.session.completed", data_obj)

    res = await client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert res.status_code == 200

    user = await _get_user(user_id)
    assert user.plan == "pro"
    assert user.stripe_customer_id == stub_stripe["customer_id"]
    assert user.stripe_subscription_id == stub_stripe["subscription_id"]
    assert user.billing_period_end is not None
    assert user.cancel_at_period_end is False


@pytest.mark.asyncio
async def test_webhook_subscription_deleted_downgrades_to_free(client, monkeypatch, stub_stripe):
    user_id, _ = await _register(client)
    await _set_user_billing(
        user_id,
        plan="pro",
        stripe_subscription_id=stub_stripe["subscription_id"],
        stripe_customer_id=stub_stripe["customer_id"],
        billing_period_end=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )

    data_obj = _FakeStripeObject(id=stub_stripe["subscription_id"])
    _fake_webhook_event(monkeypatch, "customer.subscription.deleted", data_obj)

    res = await client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert res.status_code == 200

    user = await _get_user(user_id)
    assert user.plan == "free"
    assert user.stripe_subscription_id is None
    assert user.billing_period_end is None
    assert user.sessions_used_this_month == 0


@pytest.mark.asyncio
async def test_webhook_subscription_updated_refreshes_period_end(client, monkeypatch, stub_stripe):
    user_id, _ = await _register(client)
    await _set_user_billing(
        user_id,
        plan="pro",
        stripe_subscription_id=stub_stripe["subscription_id"],
    )

    new_period_end_ts = 2_050_000_000
    data_obj = _FakeStripeObject(
        id=stub_stripe["subscription_id"],
        current_period_end=new_period_end_ts,
        cancel_at_period_end=True,
        status="active",
    )
    _fake_webhook_event(monkeypatch, "customer.subscription.updated", data_obj)

    res = await client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert res.status_code == 200

    user = await _get_user(user_id)
    assert user.cancel_at_period_end is True
    expected = datetime.fromtimestamp(new_period_end_ts, tz=timezone.utc)
    assert user.billing_period_end == expected


@pytest.mark.asyncio
async def test_webhook_returns_400_for_invalid_signature(client, monkeypatch):
    def bad_construct(*args):
        raise stripe.error.SignatureVerificationError("bad sig", "sig_header")

    monkeypatch.setattr(stripe.Webhook, "construct_event", bad_construct)

    res = await client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=bad"},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_webhook_returns_200_even_when_dispatch_raises(client, monkeypatch):
    """Stripe retries forever on non-200 — processing failures must be swallowed."""
    event = _FakeEvent("checkout.session.completed", _FakeStripeObject())
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a: event)

    async def _raise(event, db):
        raise RuntimeError("simulated internal failure")

    monkeypatch.setattr(billing_mod, "_dispatch_event", _raise)

    res = await client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert res.status_code == 200


# ══════════════════════ Session limit enforcement ═════════════════════════════


@pytest.mark.asyncio
async def test_free_user_is_blocked_at_monthly_session_limit(client):
    user_id, headers = await _register(client)
    current_month = date.today().replace(day=1)
    await _set_user_billing(
        user_id, plan="free", sessions_used_this_month=15, billing_month=current_month
    )

    res = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"scenario": "project_defense", "topic": "Test", "panelists": sample_panelists()},
    )
    assert res.status_code == 402
    assert res.json()["message"] == "session_limit_reached"


@pytest.mark.asyncio
async def test_session_creation_increments_usage_count(client):
    user_id, headers = await _register(client)
    current_month = date.today().replace(day=1)
    await _set_user_billing(
        user_id, plan="free", sessions_used_this_month=0, billing_month=current_month
    )

    await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"scenario": "project_defense", "topic": "Test", "panelists": sample_panelists()},
    )

    user = await _get_user(user_id)
    assert user.sessions_used_this_month == 1


@pytest.mark.asyncio
async def test_pro_user_can_create_sessions_beyond_free_limit(client):
    user_id, headers = await _register(client)
    await _set_user_billing(user_id, plan="pro", sessions_used_this_month=999)

    res = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"scenario": "project_defense", "topic": "Test", "panelists": sample_panelists()},
    )
    assert res.status_code == 201


@pytest.mark.asyncio
async def test_session_limit_resets_when_billing_month_rolls_over(client):
    user_id, headers = await _register(client)
    # Last month's count at cap — should reset and allow creation
    old_month = date(2020, 1, 1)
    await _set_user_billing(
        user_id, plan="free", sessions_used_this_month=15, billing_month=old_month
    )

    res = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"scenario": "project_defense", "topic": "Test", "panelists": sample_panelists()},
    )
    assert res.status_code == 201

    user = await _get_user(user_id)
    assert user.sessions_used_this_month == 1
    assert user.billing_month == date.today().replace(day=1)


# ══════════════════════ Panelist limit enforcement ════════════════════════════


@pytest.mark.asyncio
async def test_free_user_cannot_start_session_with_multiple_panelists(client):
    user_id, headers = await _register(client)
    await _set_user_billing(user_id, plan="free")
    session = await _create_session(client, headers, panelists=sample_panelists())

    res = await client.post(f"/api/v1/sessions/{session['id']}/start", headers=headers)
    assert res.status_code == 403
    assert res.json()["error_code"] == "panelist_limit_exceeded"


@pytest.mark.asyncio
async def test_free_user_can_start_session_with_one_panelist(client):
    user_id, headers = await _register(client)
    await _set_user_billing(user_id, plan="free")
    session = await _create_session(client, headers, panelists=[sample_panelists()[0]])

    res = await client.post(f"/api/v1/sessions/{session['id']}/start", headers=headers)
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_pro_user_can_start_session_with_multiple_panelists(client):
    user_id, headers = await _register(client)
    await _set_user_billing(user_id, plan="pro")
    session = await _create_session(client, headers, panelists=sample_panelists())

    res = await client.post(f"/api/v1/sessions/{session['id']}/start", headers=headers)
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_start_returns_404_for_unknown_session(client):
    headers = await registered_user_headers(client)
    res = await client.post(f"/api/v1/sessions/{uuid.uuid4()}/start", headers=headers)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_start_returns_403_for_session_owned_by_another_user(client):
    _, owner_headers = await _register(client)
    session = await _create_session(client, owner_headers)

    _, other_headers = await _register(client)
    res = await client.post(f"/api/v1/sessions/{session['id']}/start", headers=other_headers)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_start_requires_auth(client):
    res = await client.post(f"/api/v1/sessions/{uuid.uuid4()}/start")
    assert res.status_code in (401, 403)
