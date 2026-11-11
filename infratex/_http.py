"""Low-level HTTP transport for the Infratex SDK."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterator, List, Optional, Type

import httpx

from ._version import __version__

__all__ = [
    "HTTPClient",
    "InfratexError",
    "InvalidPipelineError",
    "PipelineNotAvailableError",
    "BinaryResponse",
]

_DEFAULT_BASE_URL = "https://api.infratex.io"
_DEFAULT_TIMEOUT = 300.0  # seconds


class BinaryResponse:
    """A downloaded binary payload with its suggested filename."""

    __slots__ = ("content", "filename", "content_type")

    def __init__(
        self,
        content: bytes,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> None:
        self.content = content
        self.filename = filename
        self.content_type = content_type

    def save(self, path: str) -> str:
        """Write the payload to ``path`` and return the path written."""
        with open(path, "wb") as f:
            f.write(self.content)
        return path

    def __len__(self) -> int:
        return len(self.content)

    def __repr__(self) -> str:
        return "BinaryResponse(filename={!r}, content_type={!r}, bytes={})".format(
            self.filename, self.content_type, len(self.content)
        )


class InfratexError(Exception):
    """Raised when the Infratex API returns an error response.

    ``code`` is the API's machine-readable error code (``invalid_pdf``,
    ``idempotency_key_reused``, ...). ``request_id`` identifies the request in
    support conversations. ``retry_after`` is the ``Retry-After`` header in
    seconds, set on 429 and on 409 ``idempotency_request_in_progress``.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.details = details
        self.request_id = request_id
        self.retry_after = retry_after

    def __repr__(self) -> str:
        return "{}(status_code={!r}, code={!r}, message={!r})".format(
            type(self).__name__, self.status_code, self.code, str(self)
        )


class InvalidPipelineError(InfratexError):
    """422 ``invalid_pipeline``: an extraction run's ``pipeline`` is not
    ``"legacy"`` or ``"v2"``. Nothing was created or billed."""

    @property
    def allowed_pipelines(self) -> List[str]:
        return list((self.details or {}).get("allowed_pipelines") or [])


class PipelineNotAvailableError(InfratexError):
    """422 ``pipeline_not_available``: the run asks for ``pipeline="v2"`` (beta),
    which is not open for this account yet. Omit ``pipeline`` or send
    ``"legacy"``; :meth:`~infratex.resources.extractions.Extractions.list_pipelines`
    shows what the account can choose. Nothing was created or billed."""

    @property
    def requested_pipeline(self) -> Optional[str]:
        value = (self.details or {}).get("requested_pipeline")
        return value if isinstance(value, str) else None

    @property
    def available_pipelines(self) -> List[str]:
        return list((self.details or {}).get("available_pipelines") or [])


_ERRORS_BY_CODE: Dict[str, Type[InfratexError]] = {
    "invalid_pipeline": InvalidPipelineError,
    "pipeline_not_available": PipelineNotAvailableError,
}


class HTTPClient:
    """Thin wrapper around ``httpx.Client`` with auth and error handling."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        httpx_client: Optional[httpx.Client] = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self.timeout_seconds = timeout or _DEFAULT_TIMEOUT
        # Sent on every request, so a caller-supplied httpx_client is
        # authenticated too.
        self._headers = {
            "Authorization": "Bearer {}".format(api_key),
            "User-Agent": f"infratex-python/{__version__}",
        }

        if httpx_client is not None:
            self._client = httpx_client
        else:
            self._client = httpx.Client(
                base_url=self._base_url,
                timeout=self.timeout_seconds,
                headers=self._headers,
            )

    # --------------------------------------------------------------------- #
    # Public helpers
    # --------------------------------------------------------------------- #

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Optional[str]]] = None,
    ) -> Any:
        """Send an HTTP request and return the parsed JSON body.

        ``headers`` are added to the request; ``None`` values are left out.
        """
        # Strip None values from params
        if params:
            params = {k: v for k, v in params.items() if v is not None}

        response = self._client.request(
            method,
            path,
            json=json_body,
            data=data,
            files=files,
            params=params or None,
            headers=self._request_headers(headers),
        )
        return self._handle_response(response)

    def request_text(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Send an HTTP request and return the raw text body."""
        if params:
            params = {k: v for k, v in params.items() if v is not None}

        response = self._client.request(
            method, path, params=params or None, headers=self._request_headers()
        )

        if response.status_code >= 400:
            self._raise_for_status(response)

        return response.text

    def request_no_content(
        self,
        method: str,
        path: str,
    ) -> None:
        """Send an HTTP request that returns 204 No Content."""
        response = self._client.request(method, path, headers=self._request_headers())
        if response.status_code >= 400:
            self._raise_for_status(response)

    def request_bytes(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> "BinaryResponse":
        """Send an HTTP request and return the raw response bytes + filename."""
        if params:
            params = {k: v for k, v in params.items() if v is not None}

        response = self._client.request(
            method, path, params=params or None, headers=self._request_headers()
        )
        if response.status_code >= 400:
            self._raise_for_status(response)

        filename = None
        disposition = response.headers.get("content-disposition", "")
        match = re.search(r'filename="?([^"]+)"?', disposition, re.IGNORECASE)
        if match:
            filename = match.group(1)

        return BinaryResponse(
            content=response.content,
            filename=filename,
            content_type=response.headers.get("content-type"),
        )

    def stream_sse(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Send an HTTP request and iterate over SSE ``data:`` lines."""
        with self._client.stream(
            method, path, json=json_body, headers=self._request_headers()
        ) as response:
            if response.status_code >= 400:
                # Read the full body for the error message
                response.read()
                self._raise_for_status(response)

            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[len("data: "):]
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue

    def close(self) -> None:
        self._client.close()

    # --------------------------------------------------------------------- #
    # Internal
    # --------------------------------------------------------------------- #

    def _request_headers(
        self, extra: Optional[Dict[str, Optional[str]]] = None
    ) -> Dict[str, str]:
        headers = dict(self._headers)
        for name, value in (extra or {}).items():
            if value is not None:
                headers[name] = value
        return headers

    @staticmethod
    def _handle_response(response: httpx.Response) -> Any:
        if response.status_code >= 400:
            HTTPClient._raise_for_status(response)

        # 204 No Content
        if response.status_code == 204 or not response.content:
            return None

        return response.json()

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        raise error_from_response(response)


def error_from_response(response: httpx.Response) -> InfratexError:
    """The :class:`InfratexError` (or typed subclass) for an error response.

    The API answers ``{"error": {"code", "message", "details", "request_id"}}``;
    the older top-level ``{"code", "message", "details"}`` and FastAPI's
    ``{"detail": ...}`` shapes are read too.
    """
    message = "API request failed"
    code: Optional[str] = None
    details: Any = None
    request_id: Optional[str] = response.headers.get("x-request-id")

    try:
        body = response.json()
    except Exception:
        body = None
        message = response.text or message

    if isinstance(body, dict):
        payload: Dict[str, Any] = body
        if isinstance(body.get("error"), dict):
            payload = body["error"]
        elif isinstance(body.get("detail"), dict):
            payload = body["detail"]
        elif isinstance(body.get("detail"), str):
            payload = {"message": body["detail"]}
        message = _as_str(payload.get("message")) or message
        code = _as_str(payload.get("code"))
        details = payload.get("details")
        request_id = _as_str(payload.get("request_id")) or request_id

    error_class = _ERRORS_BY_CODE.get(code or "", InfratexError)
    return error_class(
        message,
        status_code=response.status_code,
        code=code,
        details=_as_details(details),
        request_id=request_id,
        retry_after=_retry_after(response),
    )


def _as_str(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def _as_details(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    # A request validation error lists its field errors.
    return {"errors": value}


def _retry_after(response: httpx.Response) -> Optional[float]:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
