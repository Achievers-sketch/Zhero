# ADR 0003: RAG ingestion and retrieval baseline

- Status: accepted
- Date: 2026-11-24

## Scope

Blueprint RAG stages 1 (load), 2 (split), 4 (store) and 5 (retrieve). Stage 3 (embed) and
stage 6 (generate) are not built yet.

## Decisions

- **Separate upload and ingest.** `POST /documents` validates (extension, declared MIME type,
  size, magic bytes/UTF-8) and stores the original under a generated filename outside any web
  root; `POST /documents/{id}/ingest` parses and indexes. Ingest is idempotent: an ingested
  document is returned unchanged, failed or empty ones can be retried. Ingestion is synchronous
  for now (small documents); move to a background job if parsing becomes slow.
- **Honest failure states.** Encrypted, corrupt, non-UTF-8 and image-only documents get a
  `failed` or `empty` status with a clear `status_detail`; they are never silently indexed.
  Owner-password-only PDFs open with an empty user password, as in any PDF viewer.
- **pypdf instead of PyMuPDF.** The blueprint suggests PyMuPDF, which is AGPL-licensed. pypdf
  is BSD-licensed and pure Python (easy on Windows). `cryptography` is included so AES-protected
  PDFs are handled. OCR is out of scope, so scanned manuals will report `empty`.
- **Provenance on every chunk.** document ID, page start/end (null for plain text), section
  heading, chunk index and ingestion run ID. Chunks never span a section change; overlap is
  whole paragraphs so page ranges stay exact; oversized paragraphs are split on word
  boundaries. Warning/caution paragraphs are kept whole where they fit.
- **Conservative header/footer cleaning.** Only edge lines of a page are candidates, and only
  exact repeats or "Page N" markers are removed; body lines that merely differ by a number are
  kept, and lines starting with warning words are never removed.
- **Duplicate detection by SHA-256.** Re-uploading identical bytes returns 409 with the existing
  document ID. Document versioning (revision history) is not built yet; re-ingesting replaces
  that document's chunks, so chunk IDs are stable only for an unchanged ingested document.
- **BM25 baseline, no vectors yet.** Pure-Python BM25 with part-number-aware tokenisation runs
  on both PostgreSQL and SQLite with no extra services. It is rebuilt per query, which is fine
  for the MVP's small corpus. A vector (pgvector) or hybrid retriever can be added behind the
  same `search` interface once an embedding model is chosen and a benchmark exists.
- **Empty hits are a valid answer.** Search returns no hits when nothing scores above zero;
  downstream generation must say evidence is insufficient rather than invent any.
- **Retrieved text is untrusted.** It is returned as data only; later prompt construction must
  keep it separate from instructions. Retrieval logs record IDs, scores and timings, not query
  text.
- **Synthetic placeholder.** `docs/equipment_research/PLACEHOLDER_demo_ultrasound_manual.txt` is
  clearly labelled fictional and exists only for tests and demos.
