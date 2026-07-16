"""Low-level HTTP transport for the Infratex SDK."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, Optional

import httpx

from ._version import __version__

__all__ = ["HTTPClient", "InfratexError"]

_DEFAULT_BASE_URL = "https://api.infratex.io"
_DEFAULT_TIMEOUT = 300.0  # seconds


class InfratexError(Exception):
    """Raised when the Infratex API returns an error response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.details = details

    def __repr__(self) -> str:
        return "InfratexError(status_code={!r}, code={!r}, message={!r})".format(
            self.status_code, self.code, str(self)
        )


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

        if httpx_client is not None:
            self._client = httpx_client
        else:
            self._client = httpx.Client(
                base_url=self._base_url,
                timeout=self.timeout_seconds,
                headers={
                    "Authorization": "Bearer {}".format(api_key),
                    "User-Agent": f"infratex-python/{__version__}",
                },
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
    ) -> Any:
        """Send an HTTP request and return the parsed JSON body."""
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

        response = self._client.request(method, path, params=params or None)

        if response.status_code >= 400:
            self._raise_for_status(response)

        return response.text

    def request_no_content(
        self,
        method: str,
        path: str,
    ) -> None:
        """Send an HTTP request that returns 204 No Content."""
        response = self._client.request(method, path)
        if response.status_code >= 400:
            self._raise_for_status(response)

    def stream_sse(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Send an HTTP request and iterate over SSE ``data:`` lines."""
        with self._client.stream(method, path, json=json_body) as response:
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
        status_code = response.status_code
        code = None
        message = "API request failed"
        details = None

        try:
            body = response.json()
            if isinstance(body, dict):
                # The API may return {"detail": "..."} or {"code": "...", "message": "..."}
                message = body.get("message") or body.get("detail") or message
                code = body.get("code")
                details = body.get("details")
        except Exception:
            message = response.text or message

        raise InfratexError(
            message,
            status_code=status_code,
            code=code,
            details=details,
        )
