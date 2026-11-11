"""Extractions resource — structured field extraction from parsed documents."""

from __future__ import annotations

import json
import os
import time
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

from .._http import BinaryResponse, InfratexError
from .._types import ExtractionPipelines, ExtractionRun, ExtractionRunList
from .documents import (
    IDEMPOTENCY_HEADER,
    ParseMethod,
    _guess_document_mime_type,
    _guess_image_mime_type,
)

if TYPE_CHECKING:
    from .._http import HTTPClient

#: ``"infratex-phi"`` runs every step of the run on Infratex's self-hosted model.
ExtractionModel = Literal["fast", "pro", "infratex-phi"]
ExportFormat = Literal["csv", "xlsx"]
Completeness = Literal["standard", "exhaustive"]
#: ``"legacy"`` is the current engine; ``"v2"`` is the beta, open per account.
ExtractionPipeline = Literal["legacy", "v2"]

#: Longest server-side ``wait`` the API accepts, in seconds.
MAX_WAIT_SECONDS = 300

_TERMINAL_STATES = {"done", "error"}


class Extractions:
    """Interact with the extraction-run endpoints.

    Runs extract structured fields from a document's parsed Markdown. Supply
    either inline field definitions (``inline_fields``) or reference a template
    created in the dashboard (``template_id``) — exactly one is required.

    Extraction *templates* are managed from the dashboard; the public API can
    reference a template by id but cannot create or list templates.
    """

    _poll_interval_seconds = 1.5

    def __init__(self, client: HTTPClient) -> None:
        self._client = client

    def create(
        self,
        document_id: str,
        *,
        inline_fields: Optional[List[Dict[str, Any]]] = None,
        template_id: Optional[str] = None,
        inline_system_prompt: Optional[str] = None,
        model: ExtractionModel = "fast",
        include_evidence: bool = False,
        completeness: Optional[Completeness] = None,
        pipeline: Optional[ExtractionPipeline] = None,
        idempotency_key: Optional[str] = None,
    ) -> ExtractionRun:
        """Queue an extraction run against a parsed document.

        Parameters
        ----------
        document_id:
            The parsed document to extract from.
        inline_fields:
            A list of field definitions. Each field is a dict with ``name``,
            ``type`` (``"string"``, ``"number"``, ``"integer"``, ``"boolean"``,
            ``"date"``, ``"enum"``, ``"object"``, or ``"array"``), and
            ``description``. Optional per-field keys: ``instructions``,
            ``required``, ``enum_values`` (required when ``type`` is ``"enum"``),
            ``properties`` (required when ``type`` is ``"object"``), and
            ``items`` (required when ``type`` is ``"array"``).
        template_id:
            Reference a reusable extraction template created in the dashboard.
            Mutually exclusive with ``inline_fields``.
        inline_system_prompt:
            Optional system prompt. Only valid alongside ``inline_fields``.
        model:
            ``"fast"`` (default), ``"pro"``, or ``"infratex-phi"`` to run every
            step on Infratex's self-hosted model.
        include_evidence:
            When ``True``, evidence payloads are computed and returned on the run.
        completeness:
            ``"standard"`` (server default) or ``"exhaustive"``. Exhaustive reads
            every part of the document for array fields, merges and
            de-duplicates the items, then checks for missed ones. Slower, and
            bills more tokens; scalar fields are unaffected. Sent only when set.
        pipeline:
            ``"legacy"`` (the current engine, server default) or ``"v2"``
            (beta). Sent only when set. ``"v2"`` before the beta is open for
            the account raises :class:`~infratex.PipelineNotAvailableError`
            (422 ``pipeline_not_available``); any other value raises
            :class:`~infratex.InvalidPipelineError` (422 ``invalid_pipeline``).
            Nothing is created or billed then. :meth:`list_pipelines` says
            what the account can choose; ``run.pipeline`` reports the engine
            that ran once the run finishes.
        idempotency_key:
            Sent as the ``Idempotency-Key`` header. Reuse the same key when
            retrying the same request: within 24 hours the API returns the
            first run instead of creating (and billing) a second one.
        """
        body = _run_body(
            inline_fields=inline_fields,
            template_id=template_id,
            inline_system_prompt=inline_system_prompt,
            model=model,
            include_evidence=include_evidence,
            completeness=completeness,
            pipeline=pipeline,
        )
        resp = self._client.request(
            "POST",
            "/api/v1/documents/{}/extractions".format(document_id),
            json_body=body,
            headers={IDEMPOTENCY_HEADER: idempotency_key},
        )
        return ExtractionRun(resp)

    def create_from_file(
        self,
        file_path: str,
        *,
        inline_fields: Optional[List[Dict[str, Any]]] = None,
        template_id: Optional[str] = None,
        inline_system_prompt: Optional[str] = None,
        model: ExtractionModel = "fast",
        include_evidence: bool = False,
        completeness: Optional[Completeness] = None,
        pipeline: Optional[ExtractionPipeline] = None,
        method: Optional[ParseMethod] = None,
        wait: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> ExtractionRun:
        """Upload a file, parse it and extract fields from it in one call.

        ``POST /api/v1/extractions``: the run starts as soon as the parse
        ends. Parse and extraction are billed as usual; if the balance cannot
        cover both, the API answers 402 and nothing is created.

        Parameters
        ----------
        file_path:
            A PDF, a ``.docx``, or one PNG, JPEG or WebP image.
        inline_fields, template_id, inline_system_prompt, model, include_evidence, completeness, pipeline:
            The run, as in :meth:`create`. Checked before anything is uploaded
            or billed.
        method:
            Parse method. Server default ``"standard"``; with
            ``model="infratex-phi"`` the default is ``"infratex-phi"`` and only
            ``"infratex-phi"`` or ``"infratex-gamma"`` are accepted.
        wait:
            Seconds (0 to 300) the server holds the request until the run is
            ``done`` or ``error``. The run is returned either way; check
            ``run.status``, or call :meth:`wait_until_done`. Keep it below the
            client ``timeout``.
        idempotency_key:
            Sent as the ``Idempotency-Key`` header; see :meth:`create`.
        """
        body = _run_body(
            inline_fields=inline_fields,
            template_id=template_id,
            inline_system_prompt=inline_system_prompt,
            model=model,
            include_evidence=include_evidence,
            completeness=completeness,
            pipeline=pipeline,
        )
        _check_wait(wait)
        data: Dict[str, Any] = {"extraction": json.dumps(body)}
        if method is not None:
            data["method"] = method
        if wait is not None:
            data["wait"] = str(wait)

        filename = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            files = {"file": (filename, f, _guess_upload_mime_type(filename))}
            resp = self._client.request(
                "POST",
                "/api/v1/extractions",
                data=data,
                files=files,
                headers={IDEMPOTENCY_HEADER: idempotency_key},
            )
        return ExtractionRun(resp)

    def get(
        self,
        run_id: str,
        *,
        include_evidence: bool = False,
        wait: Optional[int] = None,
    ) -> ExtractionRun:
        """Retrieve a single extraction run by ID.

        ``wait`` (0 to 300 seconds) asks the server to hold the request until
        the run is ``done`` or ``error``; the run is returned either way. Keep
        it below the client ``timeout``.
        """
        _check_wait(wait)
        params: Dict[str, Any] = {}
        if include_evidence:
            params["include_evidence"] = "true"
        if wait is not None:
            params["wait"] = wait
        resp = self._client.request(
            "GET",
            "/api/v1/extractions/{}".format(run_id),
            params=params or None,
        )
        return ExtractionRun(resp)

    def list_pipelines(self) -> ExtractionPipelines:
        """The extraction pipelines and whether this account may choose each.

        ``GET /api/v1/extraction-pipelines``. ``"legacy"`` is always
        available; ``"v2"`` (beta) once the beta is open for the account.
        ``default`` is what a run without ``pipeline`` executes.
        """
        resp = self._client.request("GET", "/api/v1/extraction-pipelines")
        return ExtractionPipelines(resp)

    def list(
        self,
        document_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        include_evidence: bool = False,
    ) -> ExtractionRunList:
        """List prior extraction runs for a document."""
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if include_evidence:
            params["include_evidence"] = "true"
        resp = self._client.request(
            "GET",
            "/api/v1/documents/{}/extractions".format(document_id),
            params=params,
        )
        return ExtractionRunList(resp)

    def wait_until_done(
        self,
        run_id: str,
        *,
        include_evidence: bool = False,
    ) -> ExtractionRun:
        """Poll an extraction run until it reaches ``done`` (or raise on ``error``)."""
        deadline = time.monotonic() + self._client.timeout_seconds

        while True:
            run = self.get(run_id, include_evidence=include_evidence)
            if run.status == "done":
                return run
            if run.status == "error":
                raise InfratexError(
                    run.error_message or "Extraction failed",
                    status_code=409,
                    code="extraction_failed",
                )
            if time.monotonic() >= deadline:
                raise InfratexError(
                    "Extraction timed out",
                    status_code=504,
                    code="extraction_timeout",
                )
            time.sleep(self._poll_interval_seconds)

    def export(self, run_id: str, *, format: ExportFormat = "xlsx") -> BinaryResponse:
        """Download a completed run's tabular fields as ``csv`` or ``xlsx``.

        Only available when the result contains ``array<object>`` fields. The
        returned :class:`~infratex.BinaryResponse` carries the file bytes and a
        suggested ``filename``; call ``.save(path)`` to write it to disk.
        """
        return self._client.request_bytes(
            "GET",
            "/api/v1/extractions/{}/export".format(run_id),
            params={"format": format},
        )


def _run_body(
    *,
    inline_fields: Optional[List[Dict[str, Any]]],
    template_id: Optional[str],
    inline_system_prompt: Optional[str],
    model: ExtractionModel,
    include_evidence: bool,
    completeness: Optional[Completeness],
    pipeline: Optional[ExtractionPipeline],
) -> Dict[str, Any]:
    has_inline = inline_fields is not None
    has_template = template_id is not None
    if has_inline == has_template:
        raise ValueError("provide exactly one of inline_fields or template_id")
    if inline_system_prompt is not None and not has_inline:
        raise ValueError("inline_system_prompt is only valid with inline_fields")

    body: Dict[str, Any] = {
        "model": model,
        "include_evidence": include_evidence,
    }
    if inline_fields is not None:
        body["inline_fields"] = inline_fields
    if template_id is not None:
        body["template_id"] = template_id
    if inline_system_prompt is not None:
        body["inline_system_prompt"] = inline_system_prompt
    if completeness is not None:
        body["completeness"] = completeness
    if pipeline is not None:
        body["pipeline"] = pipeline
    return body


def _check_wait(wait: Optional[int]) -> None:
    if wait is not None and not 0 <= wait <= MAX_WAIT_SECONDS:
        raise ValueError("wait must be between 0 and {} seconds".format(MAX_WAIT_SECONDS))


def _guess_upload_mime_type(filename: str) -> str:
    image_type = _guess_image_mime_type(filename)
    if image_type != "application/octet-stream":
        return image_type
    return _guess_document_mime_type(filename)
