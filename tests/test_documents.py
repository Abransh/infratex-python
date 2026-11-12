from __future__ import annotations

from pathlib import Path

import json

import httpx
import pytest

from typing import Any, Dict, Iterator, List, Optional

from infratex import (
    BinaryResponse,
    DocumentFigure,
    DocumentLayout,
    DocumentProgress,
    DocumentRegion,
    EncryptedPDFError,
    InfratexError,
    ParseEngine,
    ParseEngines,
    ParseEngineVersionInfo,
)

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


def test_upload_sends_table_format_only_when_given(
    make_client: ClientFactory, tmp_path: Path
) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7 test")
    client, recorder = make_client(_queued)

    client.documents.upload(str(pdf), method="max", table_format="html", wait=False)
    client.documents.upload(str(pdf), wait=False)

    with_format, without_format = (multipart_parts(r) for r in recorder.requests)
    assert form_value(with_format, "table_format") == "html"
    assert "table_format" not in without_format


def test_upload_images_sends_table_format(make_client: ClientFactory, tmp_path: Path) -> None:
    page = tmp_path / "page-1.png"
    page.write_bytes(b"\x89PNG\r\n\x1a\n")
    client, recorder = make_client(_queued)

    client.documents.upload_images([str(page)], table_format="otsl", wait=False)

    parts = multipart_parts(recorder.last)
    assert recorder.last.url.path == "/api/v1/documents/images"
    assert form_value(parts, "table_format") == "otsl"


def _markdown(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="<!-- page:1 -->\n# Title", headers={"content-type": "text/markdown"})


def test_markdown_sends_no_query_by_default(make_client: ClientFactory) -> None:
    client, recorder = make_client(_markdown)

    text = client.documents.markdown("doc-1")

    assert text == "<!-- page:1 -->\n# Title"
    assert recorder.last.url.path == "/api/v1/documents/doc-1/markdown"
    assert recorder.last.url.query == b""


def test_markdown_forwards_table_format(make_client: ClientFactory) -> None:
    client, recorder = make_client(_markdown)

    client.documents.markdown("doc-1", table_format="html")

    assert dict(recorder.last.url.params) == {"table_format": "html"}


def test_markdown_sends_figure_descriptions_only_when_set(make_client: ClientFactory) -> None:
    client, recorder = make_client(_markdown)

    client.documents.markdown("doc-1", figure_descriptions=False)
    client.documents.markdown("doc-1", table_format="html", figure_descriptions=True)
    client.documents.markdown("doc-1", table_format="html")

    first, second, third = (dict(r.url.params) for r in recorder.requests)
    assert first == {"figure_descriptions": "false"}
    assert second == {"table_format": "html", "figure_descriptions": "true"}
    assert third == {"table_format": "html"}


_FIGURES = {
    "document_id": "doc-1",
    "figures": [
        {
            "name": "p2-1.png",
            "src": "figures/p2-1.png",
            "page": 2,
            "index": 1,
            "type": "chart",
            "score": 0.93,
            "bbox": [72.0, 100.5, 300.0, 280.25],
        }
    ],
}


def test_list_figures_returns_typed_figures(make_client: ClientFactory) -> None:
    client, recorder = make_client(lambda request: httpx.Response(200, json=_FIGURES))

    figures = client.documents.list_figures("doc-1")

    assert recorder.last.url.path == "/api/v1/documents/doc-1/figures"
    assert figures.document_id == "doc-1"
    assert len(figures) == 1
    (figure,) = list(figures)
    assert isinstance(figure, DocumentFigure)
    assert (figure.name, figure.src, figure.page, figure.index) == ("p2-1.png", "figures/p2-1.png", 2, 1)
    assert figure.type == "chart"
    assert figure.score == 0.93
    assert figure.bbox == [72.0, 100.5, 300.0, 280.25]


def test_list_figures_handles_documents_without_figures(make_client: ClientFactory) -> None:
    client, _ = make_client(
        lambda request: httpx.Response(200, json={"document_id": "doc-1", "figures": []})
    )

    assert len(client.documents.list_figures("doc-1")) == 0


_PNG = b"\x89PNG\r\n\x1a\nfigure-bytes"


def _png(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=_PNG, headers={"content-type": "image/png"})


def test_download_figure_returns_png_bytes(make_client: ClientFactory, tmp_path: Path) -> None:
    client, recorder = make_client(_png)

    figure = client.documents.download_figure("doc-1", "p2-1.png")

    assert recorder.last.url.path == "/api/v1/documents/doc-1/figures/p2-1.png"
    assert isinstance(figure, BinaryResponse)
    assert figure.content == _PNG
    assert figure.content_type == "image/png"
    assert figure.filename == "p2-1.png"
    saved = figure.save(str(tmp_path / "out.png"))
    assert Path(saved).read_bytes() == _PNG


def test_download_figure_accepts_the_markdown_src(make_client: ClientFactory) -> None:
    client, recorder = make_client(_png)

    client.documents.download_figure("doc-1", "figures/p2-1.png")

    assert recorder.last.url.path == "/api/v1/documents/doc-1/figures/p2-1.png"


def test_download_figure_raises_on_missing_figure(make_client: ClientFactory) -> None:
    client, _ = make_client(lambda request: httpx.Response(404, json={"detail": "Figure not found"}))

    with pytest.raises(InfratexError) as excinfo:
        client.documents.download_figure("doc-1", "p9-9.png")

    assert excinfo.value.status_code == 404
    assert str(excinfo.value) == "Figure not found"


def test_upload_sends_gamma_options_as_json(make_client: ClientFactory, tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7 test")
    client, recorder = make_client(_queued)

    client.documents.upload(
        str(pdf),
        method="infratex-gamma",
        options={"merge_tables": False, "ignore_labels": ["header", "footer"]},
        wait=False,
    )
    client.documents.upload(str(pdf), wait=False)

    with_options, without_options = (multipart_parts(r) for r in recorder.requests)
    assert json.loads(form_value(with_options, "options") or "") == {
        "merge_tables": False,
        "ignore_labels": ["header", "footer"],
    }
    assert "options" not in without_options


def test_upload_images_sends_options(make_client: ClientFactory, tmp_path: Path) -> None:
    page = tmp_path / "page-1.png"
    page.write_bytes(b"\x89PNG\r\n\x1a\n")
    client, recorder = make_client(_queued)

    client.documents.upload_images([str(page)], method="infratex-gamma", options={"unwarp": True}, wait=False)

    assert json.loads(form_value(multipart_parts(recorder.last), "options") or "") == {"unwarp": True}


def test_create_calls_send_the_idempotency_key(make_client: ClientFactory, tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7 test")
    page = tmp_path / "page-1.png"
    page.write_bytes(b"\x89PNG\r\n\x1a\n")
    index = {
        "id": "idx-1", "document_id": "doc-1", "method": "hybrid", "status": "pending",
        "created_at": "2026-11-10T10:00:00Z", "updated_at": "2026-11-10T10:00:00Z",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/indexes"):
            return httpx.Response(202, json=index)
        return _queued(request)

    client, recorder = make_client(handler)

    client.documents.upload(str(pdf), idempotency_key="upload-key", wait=False)
    client.documents.upload_images([str(page)], idempotency_key="images-key", wait=False)
    client.documents.index("doc-1", method="hybrid", idempotency_key="index-key", wait=False)
    client.documents.upload(str(pdf), wait=False)

    keys = [r.headers.get("idempotency-key") for r in recorder.requests]
    assert keys == ["upload-key", "images-key", "index-key", None]


_LAYOUT = {
    "document_id": "doc-1",
    "pages": [
        {
            "page": 1,
            "width": 1240.0,
            "height": 1754.0,
            "regions": [
                {"id": 0, "label": "title", "bbox": [100.0, 80.0, 900.0, 140.0], "content": "Annual report", "page": 1},
            ],
        }
    ],
}


def test_layout_returns_typed_pages_and_regions(make_client: ClientFactory) -> None:
    client, recorder = make_client(lambda request: httpx.Response(200, json=_LAYOUT))

    layout = client.documents.layout("doc-1")

    assert recorder.last.url.path == "/api/v1/documents/doc-1/layout"
    assert isinstance(layout, DocumentLayout)
    assert len(layout) == 1
    (page,) = list(layout)
    assert (page.page, page.width, page.height) == (1, 1240.0, 1754.0)
    (region,) = page.regions
    assert isinstance(region, DocumentRegion)
    assert (region.label, region.bbox, region.content) == ("title", [100.0, 80.0, 900.0, 140.0], "Annual report")


def test_layout_raises_for_other_methods(make_client: ClientFactory) -> None:
    client, _ = make_client(
        lambda request: httpx.Response(
            404,
            json={"error": {"code": "layout_not_available", "message": "This document has no layout.", "request_id": "r"}},
        )
    )

    with pytest.raises(InfratexError) as excinfo:
        client.documents.layout("doc-1")

    assert excinfo.value.code == "layout_not_available"


def _progress(stage: str, done: int, attempt: int = 1, updated: str = "2026-11-10T09:41:07Z") -> Dict[str, Any]:
    return {
        "stage": stage,
        "pages_done": done,
        "pages_total": 3,
        "attempt": attempt,
        "max_attempts": 3,
        "updated_at": updated,
    }


def _document(status: str, progress: Optional[Dict[str, Any]], error: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": "doc-1", "filename": "report.pdf", "status": status, "method": "standard",
        "page_count": 3, "processing_time_ms": 900, "error_message": error, "collection_id": None,
        "extraction_pages": None, "upload_time": "2026-11-10T09:40:00Z", "progress": progress,
    }


def test_get_returns_typed_progress(make_client: ClientFactory) -> None:
    client, _ = make_client(
        lambda request: httpx.Response(200, json=_document("processing", _progress("parsing", 2)))
    )

    document = client.documents.get("doc-1")

    assert isinstance(document.progress, DocumentProgress)
    progress = document.progress
    assert (progress.stage, progress.pages_done, progress.pages_total) == ("parsing", 2, 3)
    assert (progress.attempt, progress.max_attempts) == (1, 3)
    assert progress.updated_at == "2026-11-10T09:41:07Z"


def test_progress_is_none_when_absent_or_null(make_client: ClientFactory) -> None:
    client, _ = make_client(lambda request: httpx.Response(200, json=_document("parsed", None)))
    assert client.documents.get("doc-1").progress is None

    client, _ = make_client(lambda request: httpx.Response(200, json=_QUEUED))
    assert client.documents.get("doc-1").progress is None


def _sequence(*documents: Dict[str, Any]) -> Any:
    states: Iterator[Dict[str, Any]] = iter(documents)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/markdown"):
            return httpx.Response(200, text="<!-- page:1 -->", headers={"content-type": "text/markdown"})
        return httpx.Response(200, json=next(states))

    return handler


def test_wait_until_parsed_reports_each_new_progress(make_client: ClientFactory) -> None:
    client, _ = make_client(
        _sequence(
            _document("pending", _progress("queued", 0, attempt=0)),
            _document("processing", None),
            _document("processing", _progress("parsing", 1)),
            _document("processing", _progress("parsing", 1)),
            _document("processing", _progress("parsing", 1, updated="2026-11-10T09:41:37Z")),
            _document("processing", _progress("finishing", 3)),
            _document("parsed", None),
        )
    )
    client.documents._poll_interval_seconds = 0
    seen: List[DocumentProgress] = []

    uploaded = client.documents.wait_until_parsed("doc-1", on_progress=seen.append)

    assert [(p.stage, p.pages_done, p.attempt, p.updated_at) for p in seen] == [
        ("queued", 0, 0, "2026-11-10T09:41:07Z"),
        ("parsing", 1, 1, "2026-11-10T09:41:07Z"),
        ("parsing", 1, 1, "2026-11-10T09:41:37Z"),
        ("finishing", 3, 1, "2026-11-10T09:41:07Z"),
    ]
    assert uploaded.status == "parsed"
    assert uploaded.markdown == "<!-- page:1 -->"


def test_wait_until_parsed_works_without_a_callback(make_client: ClientFactory) -> None:
    client, _ = make_client(
        _sequence(_document("processing", _progress("parsing", 1)), _document("parsed", None))
    )
    client.documents._poll_interval_seconds = 0

    assert client.documents.wait_until_parsed("doc-1").status == "parsed"


def test_wait_until_parsed_raises_the_document_error_message(make_client: ClientFactory) -> None:
    message = "The PDF is password-protected, so its pages could not be read. No credits were charged."
    client, _ = make_client(
        _sequence(_document("processing", _progress("parsing", 0)), _document("error", None, error=message))
    )
    client.documents._poll_interval_seconds = 0

    with pytest.raises(InfratexError) as excinfo:
        client.documents.wait_until_parsed("doc-1")

    assert str(excinfo.value) == message
    assert excinfo.value.code == "document_processing_failed"
    assert excinfo.value.details == {"document_id": "doc-1"}


def test_wait_until_parsed_timeout_carries_the_last_progress(make_client: ClientFactory) -> None:
    client, _ = make_client(lambda request: httpx.Response(200, json=_document("processing", _progress("parsing", 2))))
    client._http.timeout_seconds = 0
    client.documents._poll_interval_seconds = 0

    with pytest.raises(InfratexError) as excinfo:
        client.documents.wait_until_parsed("doc-1")

    assert excinfo.value.code == "upload_timeout"
    assert excinfo.value.details == {"document_id": "doc-1", "progress": _progress("parsing", 2)}


def test_upload_of_a_password_protected_pdf_raises_encrypted_pdf_error(
    make_client: ClientFactory, tmp_path: Path
) -> None:
    pdf = tmp_path / "locked.pdf"
    pdf.write_bytes(b"%PDF-1.7 encrypted")
    client, _ = make_client(
        lambda request: httpx.Response(
            400,
            json={
                "error": {
                    "code": "encrypted_pdf",
                    "message": "The PDF is password-protected. Remove the password and upload it again.",
                    "request_id": "req-3",
                }
            },
        )
    )

    with pytest.raises(EncryptedPDFError) as excinfo:
        client.documents.upload(str(pdf), wait=False)

    assert isinstance(excinfo.value, InfratexError)
    assert excinfo.value.status_code == 400
    assert excinfo.value.code == "encrypted_pdf"
    assert "password-protected" in str(excinfo.value)


def test_upload_sends_engine_version_only_when_given(
    make_client: ClientFactory, tmp_path: Path
) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7 test")
    client, recorder = make_client(_queued)

    client.documents.upload(str(pdf), method="standard-ultra-2", engine_version="2.5", wait=False)
    client.documents.upload(str(pdf), method="standard-ultra-2", wait=False)

    with_version, without_version = (multipart_parts(r) for r in recorder.requests)
    assert recorder.requests[0].url.path == "/api/v1/documents"
    assert form_value(with_version, "method") == "standard-ultra-2"
    assert form_value(with_version, "engine_version") == "2.5"
    assert "engine_version" not in without_version


def test_upload_images_sends_engine_version_only_when_given(
    make_client: ClientFactory, tmp_path: Path
) -> None:
    page = tmp_path / "page-1.png"
    page.write_bytes(b"\x89PNG\r\n\x1a\n")
    client, recorder = make_client(_queued)

    client.documents.upload_images([str(page)], method="standard-ultra-2", engine_version="2.0", wait=False)
    client.documents.upload_images([str(page)], wait=False)

    with_version, without_version = (multipart_parts(r) for r in recorder.requests)
    assert recorder.requests[0].url.path == "/api/v1/documents/images"
    assert form_value(with_version, "engine_version") == "2.0"
    assert "engine_version" not in without_version


def test_upload_passes_an_unknown_engine_version_through_to_the_api(
    make_client: ClientFactory, tmp_path: Path
) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7 test")
    client, recorder = make_client(_queued)

    client.documents.upload(  # type: ignore[call-overload]
        str(pdf), method="standard-ultra-2", engine_version="3.0", wait=False
    )

    assert form_value(multipart_parts(recorder.last), "engine_version") == "3.0"


def test_documents_report_engine_version(make_client: ClientFactory) -> None:
    ultra = dict(_document("parsed", None), method="standard-ultra-2", engine_version="2.5")
    client, _ = make_client(lambda request: httpx.Response(200, json=ultra))
    assert client.documents.get("doc-1").engine_version == "2.5"

    client, _ = make_client(lambda request: httpx.Response(200, json=_QUEUED))
    assert client.documents.get("doc-1").engine_version is None


def test_waited_upload_reports_engine_version(
    make_client: ClientFactory, tmp_path: Path
) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7 test")
    parsed = dict(_document("parsed", None), method="standard-ultra-2", engine_version="2.0")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _queued(request)
        if request.url.path.endswith("/markdown"):
            return httpx.Response(200, text="<!-- page:1 -->", headers={"content-type": "text/markdown"})
        return httpx.Response(200, json=parsed)

    client, _ = make_client(handler)

    uploaded = client.documents.upload(str(pdf), method="standard-ultra-2", engine_version="2.0")

    assert uploaded.engine_version == "2.0"


_PARSE_ENGINES = [
    {"method": "standard", "versions": []},
    {
        "method": "standard-ultra-2",
        "versions": [
            {"version": "2.0", "status": "stable", "default": True},
            {"version": "2.5", "status": "beta", "default": False},
        ],
    },
]


def test_parse_engines_returns_typed_engines(make_client: ClientFactory) -> None:
    client, recorder = make_client(lambda request: httpx.Response(200, json=_PARSE_ENGINES))

    engines = client.documents.parse_engines()

    assert recorder.last.method == "GET"
    assert recorder.last.url.path == "/api/v1/parse-engines"
    assert isinstance(engines, ParseEngines)
    assert [e.method for e in engines] == ["standard", "standard-ultra-2"]
    ultra = engines.get("standard-ultra-2")
    assert isinstance(ultra, ParseEngine)
    assert all(isinstance(v, ParseEngineVersionInfo) for v in ultra.versions)
    assert [(v.version, v.status, v.default) for v in ultra.versions] == [
        ("2.0", "stable", True),
        ("2.5", "beta", False),
    ]
    assert ultra.default_version == "2.0"
    standard = engines.get("standard")
    assert standard is not None and standard.default_version is None
    assert engines.get("max") is None
    assert len(engines) == 2
