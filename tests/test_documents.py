from __future__ import annotations

from pathlib import Path

import httpx

from .conftest import ClientFactory, form_value, multipart_parts

_QUEUED = {"id": "doc-1", "filename": "report.pdf", "status": "pending", "method": "standard"}


def _queued(request: httpx.Request) -> httpx.Response:
    return httpx.Response(202, json=_QUEUED)


def test_upload_sends_infratex_gamma_method(make_client: ClientFactory, tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7 test")
    client, recorder = make_client(_queued)

    client.documents.upload(str(pdf), method="infratex-gamma", wait=False)

    parts = multipart_parts(recorder.last)
    assert recorder.last.url.path == "/api/v1/documents"
    assert form_value(parts, "method") == "infratex-gamma"


def test_upload_sends_docx_with_its_word_content_type(
    make_client: ClientFactory, tmp_path: Path
) -> None:
    docx = tmp_path / "contract.docx"
    docx.write_bytes(b"PK\x03\x04 word package")
    client, recorder = make_client(_queued)

    client.documents.upload(str(docx), wait=False)

    (file_part,) = multipart_parts(recorder.last)["file"]
    assert file_part.filename == "contract.docx"
    assert file_part.content_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert file_part.content == b"PK\x03\x04 word package"


def test_upload_keeps_pdf_content_type_for_pdfs(make_client: ClientFactory, tmp_path: Path) -> None:
    pdf = tmp_path / "Report.PDF"
    pdf.write_bytes(b"%PDF-1.7 test")
    client, recorder = make_client(_queued)

    client.documents.upload(str(pdf), wait=False)

    (file_part,) = multipart_parts(recorder.last)["file"]
    assert file_part.content_type == "application/pdf"


def test_upload_does_not_reject_other_extensions(make_client: ClientFactory, tmp_path: Path) -> None:
    unnamed = tmp_path / "scan"
    unnamed.write_bytes(b"%PDF-1.7 test")
    client, recorder = make_client(_queued)

    client.documents.upload(str(unnamed), wait=False)

    (file_part,) = multipart_parts(recorder.last)["file"]
    assert file_part.filename == "scan"
    assert file_part.content_type == "application/octet-stream"
