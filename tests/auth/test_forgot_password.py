import pytest

from tests.utils import register_user


@pytest.mark.asyncio
async def test_forgot_password_sends_reset_link_for_existing_user(client, unique_email, captured_emails):
    await register_user(client, unique_email)

    response = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": unique_email},
        headers={"Origin": "https://app.example.com"},
    )

    assert response.status_code == 200
    assert len(captured_emails) == 1
    assert captured_emails[0]["to_email"] == unique_email
    assert captured_emails[0]["reset_link"].startswith(
        "https://app.example.com/reset-password?token="
    )


@pytest.mark.asyncio
async def test_forgot_password_uses_origin_header_over_referer(client, unique_email, captured_emails):
    await register_user(client, unique_email)

    await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": unique_email},
        headers={
            "Origin": "https://app.example.com",
            "Referer": "https://other-site.example.com/some/page",
        },
    )

    assert captured_emails[0]["reset_link"].startswith("https://app.example.com/")


@pytest.mark.asyncio
async def test_forgot_password_falls_back_to_referer_when_no_origin(client, unique_email, captured_emails):
    await register_user(client, unique_email)

    await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": unique_email},
        headers={"Referer": "https://referer-site.example.com/login"},
    )

    assert captured_emails[0]["reset_link"].startswith("https://referer-site.example.com/")


@pytest.mark.asyncio
async def test_forgot_password_for_unknown_email_returns_200_without_sending(client, captured_emails):
    response = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody-here@example.com"}
    )

    assert response.status_code == 200
    assert captured_emails == []


@pytest.mark.asyncio
async def test_forgot_password_for_google_only_account_returns_200_without_sending(
    client, unique_email, captured_emails, monkeypatch
):
    async def _fake_verify(id_token: str):
        return {"sub": "google-sub-1", "email": unique_email, "name": "Grace Hopper"}

    monkeypatch.setattr("api.v1.services.auth._verify_google_id_token", _fake_verify)
    await client.post("/api/v1/auth/google", json={"id_token": "valid-token"})

    response = await client.post("/api/v1/auth/forgot-password", json={"email": unique_email})

    assert response.status_code == 200
    assert captured_emails == []


@pytest.mark.asyncio
async def test_forgot_password_rejects_missing_email_field(client):
    response = await client.post("/api/v1/auth/forgot-password", json={})

    assert response.status_code == 422
