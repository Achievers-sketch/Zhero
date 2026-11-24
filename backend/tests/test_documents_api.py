"""Document upload, ingestion, chunk inspection and retrieval tests (FR-05, FR-06, FR-07)."""

from pathlib import Path

from fastapi.testclient import TestClient

from tests.pdf_utils import encrypt_pdf, make_pdf

DOCS = "/api/v1/documents"
SEARCH = "/api/v1/search"
PLACEHOLDER = Path(__file__).resolve().parents[2] / "docs/equipment_research"
PLACEHOLDER = PLACEHOLDER / "PLACEHOLDER_demo_ultrasound_manual.txt"

MANUAL_PAGES = [
    "1 INTRODUCTION\nThis fictional manual describes the ZH-DEMO unit.",
    "2 COOLING\nA fan speed warning means the cooling fan runs slower than expected.\n"
    "Check that the ventilation openings are not blocked.",
    "3 POWER\nAn unstable power indication means the supply voltage is fluctuating.\n"
    "Part number PSU-310-A is the replacement power module.",
]


def upload(client: TestClient, data: bytes, name: str, content_type: str, **fields):
    return client.post(DOCS, files={"file": (name, data, content_type)}, data=fields)


def upload_pdf(client: TestClient, pages=None, name="manual.pdf", **fields):
    return upload(client, make_pdf(pages or MANUAL_PAGES), name, "application/pdf", **fields)


def ingested_pdf(client: TestClient, **fields) -> dict:
    document = upload_pdf(client, **fields).json()
    return client.post(f"{DOCS}/{document['document_id']}/ingest").json()


# --- upload validation -------------------------------------------------------------------------


def test_upload_pdf_stores_metadata_without_exposing_paths(client: TestClient, tmp_path) -> None:
    response = upload_pdf(
        client,
        title="Demo manual",
        publisher="Zhero test",
        revision="A",
        source_note="Synthetic test file",
        model_applicability="ZH-DEMO",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["document_id"] == "DOC-0001"
    assert body["status"] == "uploaded" and body["chunk_count"] == 0
    assert body["title"] == "Demo manual" and body["revision"] == "A"
    assert body["equipment_type"] == "Ultrasound"
    assert body["file_type"] == "pdf" and body["size_bytes"] > 0 and len(body["sha256"]) == 64
    assert "storage_key" not in body and "uploads" not in response.text
    stored = list((tmp_path / "uploads" / "DOC-0001").iterdir())
    assert len(stored) == 1 and stored[0].suffix == ".pdf"
    assert stored[0].name != "manual.pdf"  # generated filename


def test_upload_txt_defaults_title_to_filename_stem(client: TestClient) -> None:
    response = upload(client, PLACEHOLDER.read_bytes(), "notes.txt", "text/plain")
    assert response.status_code == 201
    assert response.json()["title"] == "notes" and response.json()["file_type"] == "txt"


def test_rejects_unsupported_extension_and_mime_mismatch(client: TestClient) -> None:
    assert upload(client, b"x", "a.docx", "application/vnd.ms-word").status_code == 415
    assert upload(client, b"x", "noextension", "text/plain").status_code == 415
    mismatch = upload(client, make_pdf(["x"]), "a.pdf", "text/plain")
    assert mismatch.status_code == 415
    assert mismatch.json()["error"]["code"] == "unsupported_file_type"
    assert upload(client, b"hello", "a.txt", "application/pdf").status_code == 415


def test_rejects_bad_content(client: TestClient) -> None:
    assert upload(client, b"", "a.txt", "text/plain").status_code == 422
    assert upload(client, b"not a pdf at all", "a.pdf", "application/pdf").status_code == 422
    assert upload(client, b"abc\x00def", "a.txt", "text/plain").status_code == 422


def test_rejects_oversized_files(client: TestClient) -> None:
    too_big = b"a" * (25 * 1024 * 1024 + 1)
    response = upload(client, too_big, "big.txt", "text/plain")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_filename_is_sanitised(client: TestClient) -> None:
    response = upload(client, b"hello world", "..\\..\\evil/../manual.txt", "text/plain")
    assert response.status_code == 201
    assert response.json()["original_filename"] == "manual.txt"


def test_duplicate_upload_conflicts(client: TestClient) -> None:
    assert upload_pdf(client).status_code == 201
    second = upload_pdf(client, name="copy.pdf")
    assert second.status_code == 409
    assert "DOC-0001" in second.json()["error"]["message"]


# --- ingestion ------------------------------------------------------------------------------------


def test_ingest_pdf_creates_traceable_chunks(client: TestClient) -> None:
    document = ingested_pdf(client, title="Demo manual", revision="A")
    assert document["status"] == "ingested" and document["status_detail"] is None
    assert document["page_count"] == 3 and document["chunk_count"] == 3
    assert document["parser_version"] and document["ingestion_run_id"]
    assert document["ingested_at"]

    chunks = client.get(f"{DOCS}/DOC-0001/chunks").json()
    assert chunks["total"] == 3
    first = chunks["items"][0]
    assert first["chunk_id"].startswith("CHK-") and first["document_id"] == "DOC-0001"
    assert [c["section"] for c in chunks["items"]] == ["1 INTRODUCTION", "2 COOLING", "3 POWER"]
    assert [(c["page_start"], c["page_end"]) for c in chunks["items"]] == [(1, 1), (2, 2), (3, 3)]
    assert "ventilation openings" in chunks["items"][1]["text"]


def test_ingest_text_has_no_pages_but_has_sections(client: TestClient) -> None:
    upload(client, PLACEHOLDER.read_bytes(), "placeholder.txt", "text/plain")
    document = client.post(f"{DOCS}/DOC-0001/ingest").json()
    assert document["status"] == "ingested" and document["chunk_count"] > 5
    chunks = client.get(f"{DOCS}/DOC-0001/chunks", params={"limit": 100}).json()["items"]
    assert all(c["page_start"] is None and c["page_end"] is None for c in chunks)
    sections = {c["section"] for c in chunks}
    assert (
        "2.2 Cooling and ventilation" in sections and "4.1 Cooling subsystem inspection" in sections
    )
    assert all(c["char_count"] <= 900 for c in chunks)


def test_ingest_is_idempotent(client: TestClient) -> None:
    first = ingested_pdf(client)
    second = client.post(f"{DOCS}/DOC-0001/ingest").json()
    assert second["ingestion_run_id"] == first["ingestion_run_id"]
    assert client.get(f"{DOCS}/DOC-0001/chunks").json()["total"] == 3
    assert client.get(f"{DOCS}/DOC-0001").json()["chunk_count"] == 3


def test_blank_pdf_is_reported_as_empty(client: TestClient) -> None:
    upload_pdf(client, pages=["", ""])
    document = client.post(f"{DOCS}/DOC-0001/ingest").json()
    assert document["status"] == "empty" and document["chunk_count"] == 0
    assert "OCR" in document["status_detail"]
    assert len(document["warnings"]) == 2 and "Page 1" in document["warnings"][0]


def test_password_protected_pdf_is_reported_as_failed(client: TestClient) -> None:
    upload(
        client, encrypt_pdf(make_pdf(["secret"]), user_password="pw"), "p.pdf", "application/pdf"
    )
    document = client.post(f"{DOCS}/DOC-0001/ingest").json()
    assert document["status"] == "failed"
    assert document["status_detail"].startswith("encrypted_pdf")


def test_owner_password_only_pdf_is_readable(client: TestClient) -> None:
    protected = encrypt_pdf(make_pdf(["Readable cooling text"]), user_password="")
    upload(client, protected, "o.pdf", "application/pdf")
    assert client.post(f"{DOCS}/DOC-0001/ingest").json()["status"] == "ingested"


def test_corrupt_pdf_is_reported_as_failed_and_can_be_retried(client: TestClient) -> None:
    upload(client, b"%PDF-1.4\nthis is not a real pdf body", "bad.pdf", "application/pdf")
    document = client.post(f"{DOCS}/DOC-0001/ingest").json()
    assert document["status"] == "failed" and document["status_detail"].startswith("malformed_pdf")
    assert client.post(f"{DOCS}/DOC-0001/ingest").json()["status"] == "failed"  # retry allowed
    assert client.get(f"{DOCS}/DOC-0001/chunks").json()["total"] == 0


def test_non_utf8_text_is_reported_as_failed(client: TestClient) -> None:
    upload(client, b"caf\xe9 latin-1 text", "latin.txt", "text/plain")
    document = client.post(f"{DOCS}/DOC-0001/ingest").json()
    assert document["status"] == "failed" and document["status_detail"].startswith("invalid_text")


def test_missing_stored_file_is_reported_as_failed(client: TestClient, tmp_path) -> None:
    upload_pdf(client)
    for path in (tmp_path / "uploads").rglob("*.pdf"):
        path.unlink()
    document = client.post(f"{DOCS}/DOC-0001/ingest").json()
    assert document["status"] == "failed"
    assert str(tmp_path) not in document["status_detail"]  # no internal paths leaked


def test_tampered_stored_file_is_rejected_by_checksum(client: TestClient, tmp_path) -> None:
    upload_pdf(client)
    for path in (tmp_path / "uploads").rglob("*.pdf"):
        path.write_bytes(path.read_bytes() + b"\n% tampered")
    document = client.post(f"{DOCS}/DOC-0001/ingest").json()
    assert document["status"] == "failed" and "checksum" in document["status_detail"]


# --- lookups ---


def test_list_get_and_not_found(client: TestClient) -> None:
    upload_pdf(client)
    upload(client, b"second document text", "b.txt", "text/plain")
    client.post(f"{DOCS}/DOC-0002/ingest")
    listing = client.get(DOCS).json()
    assert listing["total"] == 2 and [d["document_id"] for d in listing["items"]] == [
        "DOC-0001",
        "DOC-0002",
    ]
    assert client.get(DOCS, params={"status": "ingested"}).json()["total"] == 1
    assert client.get(DOCS, params={"status": "bogus"}).status_code == 422
    assert (
        client.get(DOCS, params={"limit": 1, "offset": 1}).json()["items"][0]["document_id"]
        == "DOC-0002"
    )
    for missing in ("DOC-0099", "nonsense", "DOC-"):
        assert client.get(f"{DOCS}/{missing}").status_code == 404
    assert client.post(f"{DOCS}/DOC-0099/ingest").status_code == 404
    assert client.get(f"{DOCS}/DOC-0099/chunks").status_code == 404


# --- retrieval ---


def test_search_returns_ranked_cited_passages(client: TestClient) -> None:
    ingested_pdf(client, title="Demo manual", revision="A")
    response = client.post(SEARCH, json={"query": "fan speed warning cooling fan"})
    assert response.status_code == 200
    body = response.json()
    assert body["retrieval_method"] == "bm25"
    top = body["hits"][0]
    assert top["rank"] == 1 and top["score"] > 0
    assert top["document_id"] == "DOC-0001" and top["document_title"] == "Demo manual"
    assert top["revision"] == "A" and top["section"] == "2 COOLING"
    assert (top["page_start"], top["page_end"]) == (2, 2)
    assert top["chunk_id"].startswith("CHK-") and "fan" in top["excerpt"].lower()
    scores = [h["score"] for h in body["hits"]]
    assert scores == sorted(scores, reverse=True)


def test_search_finds_exact_part_numbers(client: TestClient) -> None:
    ingested_pdf(client)
    hits = client.post(SEARCH, json={"query": "PSU-310-A"}).json()["hits"]
    assert hits and hits[0]["section"] == "3 POWER" and hits[0]["page_start"] == 3


def test_search_with_no_relevant_evidence_returns_empty(client: TestClient) -> None:
    ingested_pdf(client)
    assert client.post(SEARCH, json={"query": "quantum chromodynamics"}).json()["hits"] == []
    assert client.post(SEARCH, json={"query": "the of and"}).json()["hits"] == []  # stopwords only


def test_search_only_uses_ingested_documents(client: TestClient) -> None:
    upload_pdf(client)  # uploaded but not ingested
    assert client.post(SEARCH, json={"query": "cooling fan"}).json()["hits"] == []
    upload(client, make_pdf(["", ""]), "blank.pdf", "application/pdf")
    client.post(f"{DOCS}/DOC-0002/ingest")  # empty
    assert client.post(SEARCH, json={"query": "cooling"}).json()["hits"] == []


def test_search_filters_and_top_k(client: TestClient) -> None:
    ingested_pdf(client, model_applicability="ZH-DEMO Ultrasound")
    client.post(
        DOCS,
        files={
            "file": ("other.txt", b"Cooling notes for another machine. Fan cooling.", "text/plain")
        },
        data={"model_applicability": "OTHER-9", "equipment_type": "Ventilator"},
    )
    client.post(f"{DOCS}/DOC-0002/ingest")

    both = client.post(SEARCH, json={"query": "cooling fan"}).json()["hits"]
    assert {h["document_id"] for h in both} == {"DOC-0001", "DOC-0002"}
    only_first = client.post(
        SEARCH, json={"query": "cooling fan", "document_id": "DOC-0001"}
    ).json()
    assert {h["document_id"] for h in only_first["hits"]} == {"DOC-0001"}
    by_type = client.post(
        SEARCH, json={"query": "cooling fan", "equipment_type": "Ventilator"}
    ).json()
    assert {h["document_id"] for h in by_type["hits"]} == {"DOC-0002"}
    by_model = client.post(
        SEARCH, json={"query": "cooling fan", "model_applicability": "zh-demo"}
    ).json()
    assert {h["document_id"] for h in by_model["hits"]} == {"DOC-0001"}
    assert len(client.post(SEARCH, json={"query": "cooling fan", "top_k": 1}).json()["hits"]) == 1


def test_search_validation(client: TestClient) -> None:
    assert client.post(SEARCH, json={}).status_code == 422
    assert client.post(SEARCH, json={"query": ""}).status_code == 422
    assert client.post(SEARCH, json={"query": "x" * 501}).status_code == 422
    assert client.post(SEARCH, json={"query": "x", "top_k": 0}).status_code == 422
    assert client.post(SEARCH, json={"query": "x", "document_id": "bogus"}).status_code == 422
    assert client.post(SEARCH, json={"query": "x", "extra": 1}).status_code == 422


def test_search_end_to_end_on_placeholder_manual(client: TestClient) -> None:
    upload(
        client,
        PLACEHOLDER.read_bytes(),
        "placeholder.txt",
        "text/plain",
    )
    client.post(f"{DOCS}/DOC-0001/ingest")
    hits = client.post(SEARCH, json={"query": "fan speed warning blocked ventilation"}).json()[
        "hits"
    ]
    assert hits[0]["section"] in {"3.1 Fan speed warning", "2.2 Cooling and ventilation"}
    part = client.post(SEARCH, json={"query": "replacement fan part number FAN-2040-X"}).json()[
        "hits"
    ]
    assert part[0]["section"] == "4.1 Cooling subsystem inspection"
