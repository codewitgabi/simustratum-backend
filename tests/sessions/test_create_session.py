import pytest

from tests.utils import registered_user_headers, sample_panelists


@pytest.mark.asyncio
async def test_create_session_succeeds_with_minimal_body(client):
    headers = await registered_user_headers(client)

    response = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={
            "scenario": "project_defense",
            "topic": "A study on distributed consensus",
            "panelists": sample_panelists(),
        },
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["scenario"] == "project_defense"
    assert body["status"] == "pending"
    assert body["question_count"] == 0
    assert len(body["panelists"]) == 2
    assert all("id" in p for p in body["panelists"])
    assert body["document_id"] is None
    assert body["real_time_feedback"] is False
    assert body["answer_timer"] is False
    assert body["save_transcript"] is False


@pytest.mark.asyncio
async def test_create_session_honors_explicit_session_options(client):
    headers = await registered_user_headers(client)

    response = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={
            "scenario": "project_defense",
            "topic": "A study on distributed consensus",
            "panelists": sample_panelists(),
            "real_time_feedback": True,
            "answer_timer": True,
            "save_transcript": True,
        },
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["real_time_feedback"] is True
    assert body["answer_timer"] is True
    assert body["save_transcript"] is True


@pytest.mark.asyncio
async def test_create_session_with_attached_document(client, stub_external_services):
    headers = await registered_user_headers(client)

    upload = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("notes.txt", b"Some document content for the session.", "text/plain")},
    )
    document_id = upload.json()["data"]["id"]

    response = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={
            "scenario": "oral_examination",
            "topic": "Topic backed by a document",
            "document_id": document_id,
            "panelists": sample_panelists(),
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["document_id"] == document_id


@pytest.mark.asyncio
async def test_create_session_rejects_document_not_owned_by_caller(client, stub_external_services):
    other_headers = await registered_user_headers(client)
    upload = await client.post(
        "/api/v1/documents",
        headers=other_headers,
        files={"file": ("notes.txt", b"Owned by someone else.", "text/plain")},
    )
    document_id = upload.json()["data"]["id"]

    caller_headers = await registered_user_headers(client)
    response = await client.post(
        "/api/v1/sessions",
        headers=caller_headers,
        json={
            "scenario": "oral_examination",
            "topic": "Topic backed by a document",
            "document_id": document_id,
            "panelists": sample_panelists(),
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_session_rejects_nonexistent_document_id(client):
    import uuid

    headers = await registered_user_headers(client)
    response = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={
            "scenario": "oral_examination",
            "topic": "Topic",
            "document_id": str(uuid.uuid4()),
            "panelists": sample_panelists(),
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_session_rejects_invalid_document_id_format(client):
    headers = await registered_user_headers(client)
    response = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={
            "scenario": "oral_examination",
            "topic": "Topic",
            "document_id": "not-a-uuid",
            "panelists": sample_panelists(),
        },
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_session_requires_at_least_one_panelist(client):
    headers = await registered_user_headers(client)
    response = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"scenario": "project_defense", "topic": "Topic", "panelists": []},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_session_rejects_panelist_strictness_out_of_range(client):
    headers = await registered_user_headers(client)
    response = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={
            "scenario": "project_defense",
            "topic": "Topic",
            "panelists": [{"name": "Dr. X", "strictness": 150, "inquisitiveness": 50}],
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_session_rejects_invalid_scenario(client):
    headers = await registered_user_headers(client)
    response = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"scenario": "not_a_real_scenario", "topic": "Topic", "panelists": sample_panelists()},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_session_requires_authentication(client):
    response = await client.post(
        "/api/v1/sessions",
        json={"scenario": "project_defense", "topic": "Topic", "panelists": sample_panelists()},
    )

    assert response.status_code in (401, 403)
