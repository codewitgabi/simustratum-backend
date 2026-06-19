import pytest

from tests.utils import registered_user_headers


@pytest.mark.asyncio
async def test_upload_txt_document_succeeds_and_is_ready(client, stub_external_services):
    headers = await registered_user_headers(client)

    response = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("notes.txt", b"This is a plain text document about distributed systems.", "text/plain")},
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["filename"] == "notes.txt"
    assert body["status"] == "ready"
    assert body["chunk_count"] >= 1
    assert body["error_message"] is None


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_file_type(client, stub_external_services):
    headers = await registered_user_headers(client)

    response = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("archive.zip", b"PK\x03\x04fakezipcontent", "application/zip")},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_empty_file(client, stub_external_services):
    headers = await registered_user_headers(client)

    response = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("empty.txt", b"", "text/plain")},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(client, stub_external_services):
    headers = await registered_user_headers(client)
    oversized = b"a" * (15 * 1024 * 1024 + 1)

    response = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("big.txt", oversized, "text/plain")},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_requires_authentication(client, stub_external_services):
    response = await client.post(
        "/api/v1/documents",
        files={"file": ("notes.txt", b"some text", "text/plain")},
    )

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_upload_marks_document_failed_when_embedding_raises(client, monkeypatch, stub_external_services):
    headers = await registered_user_headers(client)

    async def _broken_embed(chunks: list[str]):
        raise RuntimeError("embedding provider unavailable")

    monkeypatch.setattr("api.v1.services.document_service.embed_document_chunks", _broken_embed)

    response = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("notes.txt", b"Some reasonably long document text here.", "text/plain")},
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["status"] == "failed"
    assert body["error_message"] == "Failed to embed document"
