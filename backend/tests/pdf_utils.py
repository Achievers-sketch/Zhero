"""Tiny dependency-free PDF builder for tests (text-only, one font)."""


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[str]) -> bytes:
    """Build a PDF with one page per string; newlines become separate text lines."""
    objects: list[bytes] = []
    page_ids = [4 + 2 * i for i in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, text in enumerate(pages):
        content_id = page_ids[i] + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode()
        )
        lines = text.split("\n")
        body = "BT /F1 11 Tf 14 TL 50 740 Td\n"
        body += "\n".join(f"({_escape(line)}) Tj T*" for line in lines) + "\nET"
        stream = body.encode("latin-1", "replace")
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R".encode()
        + b" >>\nstartxref\n"
        + f"{xref_at}\n%%EOF\n".encode()
    )
    return bytes(out)


def encrypt_pdf(data: bytes, *, user_password: str, algorithm: str = "AES-256") -> bytes:
    """Encrypt a PDF with pypdf (an empty ``user_password`` means owner-password-only)."""
    import io

    import pypdf

    writer = pypdf.PdfWriter()
    writer.append(pypdf.PdfReader(io.BytesIO(data)))
    writer.encrypt(user_password, "owner-secret", algorithm=algorithm)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
