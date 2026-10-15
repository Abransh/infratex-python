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
