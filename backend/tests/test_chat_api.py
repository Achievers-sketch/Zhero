"""Grounded chat tests: citations, abstention, safety, twin context, guardrails."""

import pytest
from fastapi.testclient import TestClient

from app.api.routes.chat import get_llm
from app.llm.base import GeneratedClaim, GenerationResult
from tests.test_documents_api import MANUAL_PAGES, ingested_pdf
from tests.test_twin_api import make, sim

CHAT = "/api/v1/chat"


class FakeAdapter:
    provider = "fake"
    model = "fake-1"

    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, 0

    def generate(self, request):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def use(client: TestClient, adapter) -> None:
    client.app.dependency_overrides[get_llm] = lambda: adapter


def test_answerable_question_has_server_built_citations(client: TestClient) -> None:
    ingested_pdf(client, title="Demo manual", revision="A", model_applicability="ZH-DEMO")
    response = client.post(CHAT, json={"question": "What does the fan speed warning mean?"})
    assert response.status_code == 200
    body = response.json()
    assert body["verification_status"] == "UNVERIFIED"
    assert body["chat_id"] == "CHAT-0001"
    assert body["claims"] and body["citations"]
    assert all(c["support_status"] == "UNVERIFIED" for c in body["claims"])
    cited = {c["evidence_id"] for c in body["citations"]}
    assert cited <= set(body["retrieved_chunk_ids"])
    cit = body["citations"][0]
    assert cit["document_title"] == "Demo manual" and cit["revision"] == "A"
    assert cit["page_start"] == 2
    assert body["generator"]["is_mock"] is True
    assert any("not yet been independently verified" in c for c in body["caveats"])


def test_unanswerable_question_abstains_without_model_call(client: TestClient) -> None:
    ingested_pdf(client)
    adapter = FakeAdapter()
    use(client, adapter)
    body = client.post(CHAT, json={"question": "quantum chromodynamics lattice"}).json()
    assert body["verification_status"] == "INSUFFICIENT_INFORMATION"
    assert body["claims"] == [] and body["citations"] == [] and adapter.calls == 0


def test_no_documents_is_insufficient(client: TestClient) -> None:
    body = client.post(CHAT, json={"question": "fan speed"}).json()
    assert body["verification_status"] == "INSUFFICIENT_INFORMATION"


def test_blocked_request_never_reaches_model(client: TestClient) -> None:
    ingested_pdf(client)
    adapter = FakeAdapter()
    use(client, adapter)
    body = client.post(CHAT, json={"question": "How do I bypass the thermal cutoff?"}).json()
    assert body["verification_status"] == "BLOCKED_FOR_SAFETY"
    assert "qualified" in body["answer"] and adapter.calls == 0 and body["claims"] == []


def test_invented_evidence_ids_are_discarded(client: TestClient) -> None:
    ingested_pdf(client)
    real = client.post("/api/v1/search", json={"query": "fan speed warning"}).json()["hits"][0]
    result = GenerationResult(
        answer="Answer.",
        claims=[
            GeneratedClaim("Real claim.", [real["chunk_id"], "CHK-999999"]),
            GeneratedClaim("Invented claim.", ["CHK-999999"]),
            GeneratedClaim("No citation at all.", []),
        ],
    )
    use(client, FakeAdapter(result))
    body = client.post(CHAT, json={"question": "fan speed warning"}).json()
    assert body["verification_status"] == "UNVERIFIED"
    assert [c["text"] for c in body["claims"]] == ["Real claim."]
    assert body["claims"][0]["evidence_ids"] == [real["chunk_id"]]
    assert {c["evidence_id"] for c in body["citations"]} == {real["chunk_id"]}
    assert any("2 unsupported claim" in c for c in body["caveats"])


def test_all_claims_uncited_is_insufficient(client: TestClient) -> None:
    ingested_pdf(client)
    result = GenerationResult("Confident.", [GeneratedClaim("Trust me.", ["CHK-424242"])])
    use(client, FakeAdapter(result))
    body = client.post(CHAT, json={"question": "fan speed warning"}).json()
    assert body["verification_status"] == "INSUFFICIENT_INFORMATION"
    assert body["claims"] == [] and body["answer"] != "Confident."


def test_model_abstention_respected(client: TestClient) -> None:
    ingested_pdf(client)
    result = GenerationResult("", [], abstain=True, abstention_reason="Not stated.")
    use(client, FakeAdapter(result))
    body = client.post(CHAT, json={"question": "fan speed warning"}).json()
    assert body["verification_status"] == "INSUFFICIENT_INFORMATION"
    assert body["abstention_reason"] == "Not stated."


def test_hazardous_generated_text_is_blocked(client: TestClient) -> None:
    ingested_pdf(client)
    hit = client.post("/api/v1/search", json={"query": "fan"}).json()["hits"][0]["chunk_id"]
    result = GenerationResult(
        "Just bypass the safety interlock.", [GeneratedClaim("Bypass the interlock.", [hit])]
    )
    use(client, FakeAdapter(result))
    body = client.post(CHAT, json={"question": "fan speed warning"}).json()
    assert body["verification_status"] == "BLOCKED_FOR_SAFETY" and body["claims"] == []


def test_adapter_failure_returns_502_without_details(client: TestClient) -> None:
    ingested_pdf(client)
    use(client, FakeAdapter(error=RuntimeError("secret-key-123")))
    response = client.post(CHAT, json={"question": "fan speed warning"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "llm_error"
    assert "secret" not in response.text


def test_twin_context_labelled_simulated_and_widens_retrieval(client: TestClient) -> None:
    ingested_pdf(client)
    make(client)
    assert sim(client, scenario="cooling_degradation", steps=30).status_code == 200
    body = client.post(
        CHAT, json={"question": "What should I check?", "equipment_id": "ZH-ULT-001"}
    ).json()
    assert body["twin_context_used"] is True
    assert body["twin_observations"] and all(o["simulation"] for o in body["twin_observations"])
    assert "cooling" in body["retrieval_query"]
    assert any("SIMULATED" in c for c in body["caveats"])
    assert body["verification_status"] == "UNVERIFIED" and body["citations"]


def test_no_hint_without_active_scenario(client: TestClient) -> None:
    ingested_pdf(client)
    make(client)
    sim(client, steps=3)
    body = client.post(
        CHAT, json={"question": "fan speed warning", "equipment_id": "ZH-ULT-001"}
    ).json()
    assert body["retrieval_query"] == "fan speed warning"


def test_unknown_equipment_404(client: TestClient) -> None:
    response = client.post(CHAT, json={"question": "fan", "equipment_id": "NOPE"})
    assert response.status_code == 404


@pytest.mark.parametrize(
    "payload", [{"question": ""}, {"question": "x" * 1001}, {}, {"question": "a", "x": 1}]
)
def test_validation(client: TestClient, payload) -> None:
    assert client.post(CHAT, json=payload).status_code == 422


def test_get_chat_roundtrip(client: TestClient) -> None:
    ingested_pdf(client)
    created = client.post(CHAT, json={"question": "fan speed warning"}).json()
    fetched = client.get(f"{CHAT}/{created['chat_id']}")
    assert fetched.status_code == 200 and fetched.json() == created
    assert client.get(f"{CHAT}/CHAT-9999").status_code == 404
    assert client.get(f"{CHAT}/garbage").status_code == 404


def test_uses_manual_text_only(client: TestClient) -> None:
    ingested_pdf(client)
    body = client.post(CHAT, json={"question": "What is the replacement power module part?"}).json()
    corpus = " ".join(MANUAL_PAGES)
    for claim in body["claims"]:
        assert claim["text"].split(". ")[0][:30] in corpus
