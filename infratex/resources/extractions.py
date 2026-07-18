"""Extractions resource — structured field extraction from parsed documents."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

from .._http import BinaryResponse, InfratexError
from .._types import ExtractionRun, ExtractionRunList

if TYPE_CHECKING:
    from .._http import HTTPClient

ExtractionModel = Literal["fast", "pro"]
ExportFormat = Literal["csv", "xlsx"]

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
            ``"fast"`` (default) or ``"pro"``.
        include_evidence:
            When ``True``, evidence payloads are computed and returned on the run.
        """
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

        resp = self._client.request(
            "POST",
            "/api/v1/documents/{}/extractions".format(document_id),
            json_body=body,
        )
        return ExtractionRun(resp)

    def get(self, run_id: str, *, include_evidence: bool = False) -> ExtractionRun:
        """Retrieve a single extraction run by ID."""
        params = {"include_evidence": "true"} if include_evidence else None
        resp = self._client.request(
            "GET",
            "/api/v1/extractions/{}".format(run_id),
            params=params,
        )
        return ExtractionRun(resp)

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
