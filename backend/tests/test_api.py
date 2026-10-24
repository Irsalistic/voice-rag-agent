def _events(client, message: str, session_id: str | None = None) -> list[dict]:
    payload = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    with client.stream("POST", "/api/chat", json=payload) as response:
        assert response.status_code == 200
        body = response.read().decode()
    events = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                import json

                events.append(json.loads(line[5:].strip()))
    return events


def test_health_reports_local_providers(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "extractive"
    assert body["embedding_provider"] == "hashing"
    assert body["stt_provider"] == "none"


def test_sample_documents_are_loaded(client):
    names = {item["filename"] for item in client.get("/api/documents").json()["documents"]}
    assert "refund-policy.md" in names
    assert "product-faq.md" in names


def test_chat_cites_the_refund_policy(client):
    events = _events(client, "How many days do I have to return an item?")
    kinds = [event["type"] for event in events]
    assert "token" in kinds
    assert "sources" in kinds
    assert "done" in kinds
    text = "".join(event.get("text", "") for event in events if event["type"] == "token")
    assert "30 days" in text
    sources = next(event["sources"] for event in events if event["type"] == "sources")
    assert sources[0]["source"] == "refund-policy.md"


def test_order_lookup_and_booking_round_trip(client):
    order_events = _events(client, "Where is order ORD-1001?")
    order_text = "".join(
        event.get("text", "") for event in order_events if event["type"] == "token"
    )
    assert "shipped" in order_text.lower()
    assert "NL482193" in order_text

    created = client.post("/api/sessions").json()
    session_id = created["id"]
    first = _events(client, "Please book an appointment", session_id)
    ask = "".join(event.get("text", "") for event in first if event["type"] == "token")
    assert "email" in ask.lower()
    second = _events(
        client,
        "Priya Shah, priya@example.com, 2026-11-03 at 14:00 about a damaged lamp",
        session_id,
    )
    booked = "".join(event.get("text", "") for event in second if event["type"] == "token")
    assert "APT-" in booked
    assert "confirmed" in booked.lower()
    overview = client.get("/api/admin/overview").json()
    assert any(item["email"] == "priya@example.com" for item in overview["appointments"])
    assert any(item["name"] == "lookup_order" for item in overview["tool_calls"])


def test_upload_and_delete_round_trip(client):
    response = client.post(
        "/api/documents",
        files={"file": ("warehouse.txt", b"The warehouse gate code is maple-17.", "text/plain")},
    )
    assert response.status_code == 200
    document_id = response.json()["id"]
    listed = client.get(f"/api/documents/{document_id}")
    assert listed.status_code == 200
    assert "maple-17" in listed.json()["chunks"][0]["snippet"]
    assert client.delete(f"/api/documents/{document_id}").status_code == 200
    assert client.get(f"/api/documents/{document_id}").status_code == 404


def test_voice_socket_answers_from_text(client):
    with client.websocket_connect("/api/voice/ws") as socket:
        socket.send_json({"type": "start"})
        ready = socket.receive_json()
        assert ready["type"] == "ready"
        socket.send_json({"type": "text", "text": "Are opened candles refundable?"})
        seen = []
        while True:
            message = socket.receive_json()
            seen.append(message)
            if message["type"] in {"done", "error"}:
                break
    kinds = [message["type"] for message in seen]
    assert "transcript" in kinds
    assert "token" in kinds
    assert message["type"] == "done"
    text = "".join(item.get("text", "") for item in seen if item["type"] == "token")
    assert "not refundable" in text.lower()
