"""Shared fixtures: an Infratex client wired to an in-process mock transport."""

from __future__ import annotations

from email.message import Message
from email.parser import BytesParser
from typing import Callable, Dict, Iterator, List, NamedTuple, Optional, Tuple

import httpx
import pytest

from infratex import Infratex

Handler = Callable[[httpx.Request], httpx.Response]


class Recorder:
    """Transport handler that records every request before answering it."""

    def __init__(self, handler: Handler) -> None:
        self._handler = handler
        self.requests: List[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        return self._handler(request)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]


ClientFactory = Callable[[Handler], Tuple[Infratex, Recorder]]


@pytest.fixture
def make_client() -> Iterator[ClientFactory]:
    clients: List[Infratex] = []

    def factory(handler: Handler) -> Tuple[Infratex, Recorder]:
        recorder = Recorder(handler)
        http = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(recorder))
        client = Infratex(api_key="infratex_sk_test", httpx_client=http)
        clients.append(client)
        return client, recorder

    yield factory
    for client in clients:
        client.close()


class Part(NamedTuple):
    filename: Optional[str]
    content_type: str
    content: bytes


def multipart_parts(request: httpx.Request) -> Dict[str, List[Part]]:
    """Decode a multipart/form-data request body into its named parts."""
    head = "Content-Type: {}\r\n\r\n".format(request.headers["content-type"]).encode()
    message = BytesParser().parsebytes(head + request.content)
    parts: Dict[str, List[Part]] = {}
    for part in message.get_payload():
        assert isinstance(part, Message)
        name = part.get_param("name", header="content-disposition")
        assert isinstance(name, str)
        payload = part.get_payload(decode=True)
        assert isinstance(payload, bytes)
        parts.setdefault(name, []).append(
            Part(part.get_filename(), part.get_content_type(), payload)
        )
    return parts


def form_value(parts: Dict[str, List[Part]], name: str) -> Optional[str]:
    values = parts.get(name)
    return values[0].content.decode() if values else None
