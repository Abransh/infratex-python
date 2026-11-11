from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from infratex import ExtractionPipelines

from .conftest import ClientFactory, form_value, multipart_parts

_FIELDS = [{"name": "line_items", "type": "array", "description": "Every line item",
            "items": {"name": "item", "type": "string", "description": "One line item"}}]


def _run(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    return httpx.Response(
        202,
        json={
            "id": "run-1",
            "document_id": "doc-1",
            "template_id": None,
            "status": "pending",
            "tier": None,
            "model": body["model"],
            "completeness": body.get("completeness", "standard"),
            "result": None,
            "evidence": None,
            "credits_charged": None,
            "engine_version": None,
            "pipeline": None,
            "cached": False,
            "created_at": "2026-10-15T10:00:00Z",
            "updated_at": "2026-10-15T10:00:00Z",
        },
    )


def test_create_sends_exhaustive_completeness(make_client: ClientFactory) -> None:
    client, recorder = make_client(_run)

    run = client.extractions.create("doc-1", inline_fields=_FIELDS, completeness="exhaustive")

    assert recorder.last.url.path == "/api/v1/documents/doc-1/extractions"
    assert json.loads(recorder.last.content) == {
        "model": "fast",
        "include_evidence": False,
        "inline_fields": _FIELDS,
        "completeness": "exhaustive",
    }
    assert run.completeness == "exhaustive"


def test_create_omits_completeness_by_default(make_client: ClientFactory) -> None:
    client, recorder = make_client(_run)

    run = client.extractions.create("doc-1", template_id="tpl-1")

    assert "completeness" not in json.loads(recorder.last.content)
    assert run.completeness == "standard"


def test_create_sends_pipeline_only_when_set(make_client: ClientFactory) -> None:
    client, recorder = make_client(_run)

    client.extractions.create("doc-1", template_id="tpl-1", pipeline="v2")
    client.extractions.create("doc-1", template_id="tpl-1")

    with_pipeline, without_pipeline = (json.loads(r.content) for r in recorder.requests)
    assert with_pipeline["pipeline"] == "v2"
    assert "pipeline" not in without_pipeline
    # Never a query parameter: the API answers 422 invalid_pipeline to that.
    assert all(r.url.query == b"" for r in recorder.requests)


def test_create_accepts_the_infratex_phi_model(make_client: ClientFactory) -> None:
    client, recorder = make_client(_run)

    run = client.extractions.create("doc-1", template_id="tpl-1", model="infratex-phi")

    assert json.loads(recorder.last.content)["model"] == "infratex-phi"
    assert run.model == "infratex-phi"


def test_create_sends_the_idempotency_key_header(make_client: ClientFactory) -> None:
    client, recorder = make_client(_run)

    client.extractions.create("doc-1", template_id="tpl-1", idempotency_key="key-1")
    client.extractions.create("doc-1", template_id="tpl-1")

    first, second = recorder.requests
    assert first.headers["idempotency-key"] == "key-1"
    assert "idempotency-key" not in second.headers


def test_run_reports_pipeline_cost_and_cache(make_client: ClientFactory) -> None:
    done = {
        "id": "run-1", "document_id": "doc-1", "template_id": None, "status": "done", "tier": "S",
        "model": "fast", "completeness": "standard", "result": {"a": 1}, "evidence": None,
        "credits_charged": 25.5, "engine_version": "2026.11.1", "pipeline": "v2", "cached": False,
        "created_at": "2026-10-15T10:00:00Z", "updated_at": "2026-10-15T10:01:00Z",
    }
    client, _ = make_client(lambda request: httpx.Response(200, json=done))

    run = client.extractions.get("run-1")

    assert (run.pipeline, run.credits_charged, run.engine_version, run.cached) == (
        "v2", 25.5, "2026.11.1", False
    )


def test_get_forwards_wait(make_client: ClientFactory) -> None:
    client, recorder = make_client(_run_done)

    client.extractions.get("run-1", wait=60, include_evidence=True)
    client.extractions.get("run-1")

    first, second = recorder.requests
    assert dict(first.url.params) == {"include_evidence": "true", "wait": "60"}
    assert second.url.query == b""


@pytest.mark.parametrize("wait", [-1, 301])
def test_get_rejects_out_of_range_wait(make_client: ClientFactory, wait: int) -> None:
    client, recorder = make_client(_run_done)

    with pytest.raises(ValueError, match="between 0 and 300"):
        client.extractions.get("run-1", wait=wait)
    assert recorder.requests == []


def _run_done(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"id": "run-1", "document_id": "doc-1", "template_id": None, "status": "done",
              "model": "fast", "created_at": "2026-10-15T10:00:00Z", "updated_at": "2026-10-15T10:00:00Z"},
    )


_PIPELINES = {
    "default": "legacy",
    "pipelines": [
        {"id": "legacy", "label": "Standard", "stage": "stable", "available": True},
        {"id": "v2", "label": "v2", "stage": "beta", "available": False},
    ],
}


def test_list_pipelines(make_client: ClientFactory) -> None:
    client, recorder = make_client(lambda request: httpx.Response(200, json=_PIPELINES))

    pipelines = client.extractions.list_pipelines()

    assert recorder.last.method == "GET"
    assert recorder.last.url.path == "/api/v1/extraction-pipelines"
    assert isinstance(pipelines, ExtractionPipelines)
    assert pipelines.default == "legacy"
    assert [(p.id, p.stage, p.available) for p in pipelines] == [
        ("legacy", "stable", True),
        ("v2", "beta", False),
    ]
    assert pipelines.is_available("legacy")
    assert not pipelines.is_available("v2")


def test_create_from_file_sends_the_run_as_extraction_json(
    make_client: ClientFactory, tmp_path: Path
) -> None:
    pdf = tmp_path / "contract.pdf"
    pdf.write_bytes(b"%PDF-1.7 test")
    client, recorder = make_client(_run_done)

    run = client.extractions.create_from_file(
        str(pdf),
        inline_fields=_FIELDS,
        model="pro",
        completeness="exhaustive",
        pipeline="v2",
        method="max",
        wait=120,
        idempotency_key="key-2",
    )

    request = recorder.last
    assert request.method == "POST"
    assert request.url.path == "/api/v1/extractions"
    assert request.url.query == b""
    assert request.headers["idempotency-key"] == "key-2"
    parts = multipart_parts(request)
    (file_part,) = parts["file"]
    assert (file_part.filename, file_part.content_type) == ("contract.pdf", "application/pdf")
    assert form_value(parts, "method") == "max"
    assert form_value(parts, "wait") == "120"
    assert json.loads(form_value(parts, "extraction") or "") == {
        "model": "pro",
        "include_evidence": False,
        "inline_fields": _FIELDS,
        "completeness": "exhaustive",
        "pipeline": "v2",
    }
    assert run.status == "done"


def test_create_from_file_sends_images_with_their_type(
    make_client: ClientFactory, tmp_path: Path
) -> None:
    page = tmp_path / "invoice.JPG"
    page.write_bytes(b"\xff\xd8\xff")
    client, recorder = make_client(_run_done)

    client.extractions.create_from_file(str(page), template_id="tpl-1")

    parts = multipart_parts(recorder.last)
    assert parts["file"][0].content_type == "image/jpeg"
    assert "method" not in parts and "wait" not in parts
    assert "idempotency-key" not in recorder.last.headers


def test_create_from_file_validates_before_sending(make_client: ClientFactory, tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    client, recorder = make_client(_run_done)

    with pytest.raises(ValueError, match="exactly one"):
        client.extractions.create_from_file(str(pdf))
    with pytest.raises(ValueError, match="between 0 and 300"):
        client.extractions.create_from_file(str(pdf), template_id="tpl-1", wait=301)
    assert recorder.requests == []
