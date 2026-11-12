from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Type

import httpx
import pytest

from infratex import (
    EngineVersionNotSupportedError,
    InfratexError,
    InvalidEngineVersionError,
    InvalidPipelineError,
    PipelineNotAvailableError,
)

from .conftest import ClientFactory


def _error(status: int, body: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Any:
    return lambda request: httpx.Response(status, json=body, headers=headers)


def test_reads_the_api_error_envelope(make_client: ClientFactory) -> None:
    client, _ = make_client(
        _error(
            409,
            {
                "error": {
                    "code": "idempotency_request_in_progress",
                    "message": "A request with this Idempotency-Key is still running",
                    "request_id": "req-123",
                    "details": {"key": "k-1"},
                }
            },
            headers={"Retry-After": "2"},
        )
    )

    with pytest.raises(InfratexError) as excinfo:
        client.documents.get("doc-1")

    error = excinfo.value
    assert type(error) is InfratexError
    assert error.status_code == 409
    assert error.code == "idempotency_request_in_progress"
    assert str(error) == "A request with this Idempotency-Key is still running"
    assert error.details == {"key": "k-1"}
    assert error.request_id == "req-123"
    assert error.retry_after == 2.0


def test_reads_the_top_level_and_detail_shapes(make_client: ClientFactory) -> None:
    client, _ = make_client(
        _error(404, {"code": "not_found", "message": "Document not found", "details": None})
    )
    with pytest.raises(InfratexError) as top_level:
        client.documents.get("doc-1")
    assert (top_level.value.code, str(top_level.value)) == ("not_found", "Document not found")

    client, _ = make_client(
        _error(403, {"detail": {"code": "dashboard_only", "message": "Use the dashboard", "details": None}})
    )
    with pytest.raises(InfratexError) as nested:
        client.account.settings()
    assert (nested.value.code, str(nested.value)) == ("dashboard_only", "Use the dashboard")


def test_falls_back_to_the_request_id_header_and_text_body(make_client: ClientFactory) -> None:
    client, _ = make_client(
        lambda request: httpx.Response(502, text="Bad gateway", headers={"X-Request-ID": "req-9"})
    )

    with pytest.raises(InfratexError) as excinfo:
        client.documents.get("doc-1")

    assert str(excinfo.value) == "Bad gateway"
    assert excinfo.value.code is None
    assert excinfo.value.request_id == "req-9"
    assert excinfo.value.retry_after is None


def test_keeps_validation_errors_under_details_errors(make_client: ClientFactory) -> None:
    errors = [{"loc": ["body", "query"], "msg": "Field required", "type": "missing"}]
    client, _ = make_client(
        _error(422, {"error": {"code": "validation_error", "message": "Request validation failed", "details": errors}})
    )

    with pytest.raises(InfratexError) as excinfo:
        client.searches.create(query="x")

    assert excinfo.value.code == "validation_error"
    assert excinfo.value.details == {"errors": errors}


def test_invalid_pipeline_is_typed(make_client: ClientFactory) -> None:
    client, _ = make_client(
        _error(
            422,
            {
                "error": {
                    "code": "invalid_pipeline",
                    "message": "'pipeline' must be one of 'legacy', 'v2'.",
                    "request_id": "req-1",
                    "details": {"allowed_pipelines": ["legacy", "v2"]},
                }
            },
        )
    )

    with pytest.raises(InvalidPipelineError) as excinfo:
        client.extractions.create("doc-1", template_id="tpl-1", pipeline="v3")  # type: ignore[arg-type]

    assert isinstance(excinfo.value, InfratexError)
    assert excinfo.value.status_code == 422
    assert excinfo.value.allowed_pipelines == ["legacy", "v2"]


def test_pipeline_not_available_is_typed(make_client: ClientFactory) -> None:
    client, _ = make_client(
        _error(
            422,
            {
                "error": {
                    "code": "pipeline_not_available",
                    "message": "The v2 extraction pipeline (beta) is not enabled for this account.",
                    "request_id": "req-2",
                    "details": {"requested_pipeline": "v2", "available_pipelines": ["legacy"]},
                }
            },
        )
    )

    with pytest.raises(PipelineNotAvailableError) as excinfo:
        client.extractions.create("doc-1", template_id="tpl-1", pipeline="v2")

    assert excinfo.value.code == "pipeline_not_available"
    assert excinfo.value.requested_pipeline == "v2"
    assert excinfo.value.available_pipelines == ["legacy"]
    assert excinfo.value.request_id == "req-2"


@pytest.mark.parametrize(
    "code, error_class, allowed",
    [
        ("invalid_engine_version", InvalidEngineVersionError, ["2.0", "2.5"]),
        ("engine_version_not_supported", EngineVersionNotSupportedError, ["standard-ultra-2"]),
    ],
)
def test_engine_version_refusals_are_typed(
    make_client: ClientFactory,
    tmp_path: Path,
    code: str,
    error_class: Type[InfratexError],
    allowed: List[str],
) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7 test")
    client, _ = make_client(
        _error(
            422,
            {
                "error": {
                    "code": code,
                    "message": "Refused.",
                    "request_id": "req-4",
                    "details": {"allowed": allowed},
                }
            },
        )
    )

    with pytest.raises(error_class) as excinfo:
        client.documents.upload(str(pdf), method="standard-ultra-2", engine_version="2.5", wait=False)

    error = excinfo.value
    assert isinstance(error, InfratexError)
    assert (error.status_code, error.code, error.request_id) == (422, code, "req-4")
    assert getattr(error, "allowed") == allowed


def test_allowed_is_empty_without_details(make_client: ClientFactory, tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7 test")
    client, _ = make_client(
        _error(422, {"error": {"code": "engine_version_not_supported", "message": "Refused.", "details": None}})
    )

    with pytest.raises(EngineVersionNotSupportedError) as excinfo:
        client.documents.upload(str(pdf), method="max", engine_version="2.5", wait=False)

    assert excinfo.value.allowed == []


def test_streamed_responses_raise_the_same_errors(make_client: ClientFactory) -> None:
    client, _ = make_client(
        _error(422, {"error": {"code": "data_policy_violation", "message": "Not in the EU", "details": None}})
    )

    with pytest.raises(InfratexError) as excinfo:
        list(client.responses.create(message="hi"))

    assert excinfo.value.code == "data_policy_violation"
