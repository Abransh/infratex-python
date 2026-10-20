from __future__ import annotations

import httpx

from infratex import Document

from .conftest import ClientFactory


def test_documents_get_hits_the_document_route(make_client: ClientFactory) -> None:
    client, recorder = make_client(
        lambda request: httpx.Response(
            200,
            json={"id": "doc-1", "filename": "a.pdf", "status": "parsed", "method": "standard"},
        )
    )

    document = client.documents.get("doc-1")

    assert isinstance(document, Document)
    assert document.status == "parsed"
    assert recorder.last.method == "GET"
    assert recorder.last.url.path == "/api/v1/documents/doc-1"
