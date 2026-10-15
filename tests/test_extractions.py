from __future__ import annotations

import json

import httpx

from .conftest import ClientFactory

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
