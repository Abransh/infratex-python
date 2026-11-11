from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Dict

import httpx
import pytest

from infratex import Webhook, WebhookDelivery, verify_webhook_signature

from .conftest import ClientFactory

_WEBHOOK: Dict[str, Any] = {
    "id": "wh-1",
    "url": "https://example.com/infratex",
    "description": "prod",
    "events": ["document.parsed"],
    "enabled": True,
    "created_at": "2026-11-10T10:00:00Z",
    "updated_at": "2026-11-10T10:00:00Z",
}

_DELIVERY: Dict[str, Any] = {
    "id": "del-1",
    "event_id": "evt_abc",
    "event_type": "webhook.test",
    "status": "pending",
    "attempts": 0,
    "last_status_code": None,
    "last_error": None,
    "created_at": "2026-11-10T10:00:00Z",
    "last_attempt_at": None,
    "delivered_at": None,
    "next_attempt_at": "2026-11-10T10:00:00Z",
}


def _body(request: httpx.Request) -> Any:
    return json.loads(request.content) if request.content else None


def test_create_returns_the_secret(make_client: ClientFactory) -> None:
    client, recorder = make_client(
        lambda request: httpx.Response(201, json=dict(_WEBHOOK, secret="whsec_abc"))
    )

    webhook = client.webhooks.create(
        url="https://example.com/infratex", events=["document.parsed"], description="prod"
    )

    assert (recorder.last.method, recorder.last.url.path) == ("POST", "/api/v1/webhooks")
    assert _body(recorder.last) == {
        "url": "https://example.com/infratex",
        "events": ["document.parsed"],
        "description": "prod",
    }
    assert isinstance(webhook, Webhook)
    assert webhook.secret == "whsec_abc"


def test_create_sends_only_the_url_by_default(make_client: ClientFactory) -> None:
    client, recorder = make_client(lambda request: httpx.Response(201, json=dict(_WEBHOOK, secret="s")))

    client.webhooks.create(url="https://example.com/infratex")

    assert _body(recorder.last) == {"url": "https://example.com/infratex"}


def test_list_and_get_have_no_secret(make_client: ClientFactory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/webhooks":
            return httpx.Response(200, json=[_WEBHOOK])
        return httpx.Response(200, json=_WEBHOOK)

    client, recorder = make_client(handler)

    (listed,) = client.webhooks.list()
    fetched = client.webhooks.get("wh-1")

    assert [r.url.path for r in recorder.requests] == ["/api/v1/webhooks", "/api/v1/webhooks/wh-1"]
    assert listed.secret is None and fetched.id == "wh-1"


def test_update_sends_only_given_fields(make_client: ClientFactory) -> None:
    client, recorder = make_client(lambda request: httpx.Response(200, json=_WEBHOOK))

    client.webhooks.update("wh-1", enabled=False)
    client.webhooks.update("wh-1", events=[], clear_description=True)

    first, second = recorder.requests
    assert (first.method, first.url.path) == ("PATCH", "/api/v1/webhooks/wh-1")
    assert _body(first) == {"enabled": False}
    assert _body(second) == {"events": [], "description": None}


def test_update_rejects_empty_and_conflicting_arguments(make_client: ClientFactory) -> None:
    client, recorder = make_client(lambda request: httpx.Response(200, json=_WEBHOOK))

    with pytest.raises(ValueError, match="update requires"):
        client.webhooks.update("wh-1")
    with pytest.raises(ValueError, match="cannot be used together"):
        client.webhooks.update("wh-1", description="x", clear_description=True)
    assert recorder.requests == []


def test_delete_rotate_test_and_retry(make_client: ClientFactory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.path.endswith("/rotate-secret"):
            return httpx.Response(200, json={"secret": "whsec_new"})
        return httpx.Response(202, json=_DELIVERY)

    client, recorder = make_client(handler)

    client.webhooks.delete("wh-1")
    secret = client.webhooks.rotate_secret("wh-1")
    test = client.webhooks.test("wh-1")
    retried = client.webhooks.retry_delivery("wh-1", "del-1")

    assert [(r.method, r.url.path) for r in recorder.requests] == [
        ("DELETE", "/api/v1/webhooks/wh-1"),
        ("POST", "/api/v1/webhooks/wh-1/rotate-secret"),
        ("POST", "/api/v1/webhooks/wh-1/test"),
        ("POST", "/api/v1/webhooks/wh-1/deliveries/del-1/retry"),
    ]
    assert secret.secret == "whsec_new"
    assert isinstance(test, WebhookDelivery) and test.event_type == "webhook.test"
    assert retried.id == "del-1"


def test_list_deliveries_forwards_filters(make_client: ClientFactory) -> None:
    client, recorder = make_client(lambda request: httpx.Response(200, json={"items": [_DELIVERY]}))

    deliveries = client.webhooks.list_deliveries("wh-1", status="failed", limit=10)
    client.webhooks.list_deliveries("wh-1")

    first, second = recorder.requests
    assert first.url.path == "/api/v1/webhooks/wh-1/deliveries"
    assert dict(first.url.params) == {"status": "failed", "limit": "10"}
    assert second.url.query == b""
    (delivery,) = list(deliveries)
    assert delivery.status == "pending"


def test_list_deliveries_rejects_out_of_range_limit(make_client: ClientFactory) -> None:
    client, recorder = make_client(lambda request: httpx.Response(200, json={"items": []}))

    with pytest.raises(ValueError, match="between 1 and 100"):
        client.webhooks.list_deliveries("wh-1", limit=101)
    assert recorder.requests == []


_SECRET = "whsec_test"
_PAYLOAD = b'{"id":"evt_1","type":"document.parsed"}'


def _signature(timestamp: int, body: bytes = _PAYLOAD, secret: str = _SECRET) -> str:
    digest = hmac.new(secret.encode(), "{}.".format(timestamp).encode() + body, hashlib.sha256).hexdigest()
    return "t={},v1={}".format(timestamp, digest)


def test_verify_webhook_signature_accepts_a_valid_recent_signature() -> None:
    header = _signature(1_800_000_000)

    assert verify_webhook_signature(_SECRET, _PAYLOAD, header, now=1_800_000_100)
    assert verify_webhook_signature(_SECRET, _PAYLOAD.decode(), header, now=1_800_000_000)


def test_verify_webhook_signature_accepts_any_matching_v1() -> None:
    header = _signature(1_800_000_000) + ",v1=" + "0" * 64

    assert verify_webhook_signature(_SECRET, _PAYLOAD, "v1=" + "0" * 64 + "," + header, now=1_800_000_000)


@pytest.mark.parametrize(
    ("body", "secret", "header", "now"),
    [
        (b'{"id":"evt_2"}', _SECRET, _signature(1_800_000_000), 1_800_000_000),
        (_PAYLOAD, "whsec_other", _signature(1_800_000_000), 1_800_000_000),
        (_PAYLOAD, _SECRET, _signature(1_800_000_000), 1_800_000_301),
        (_PAYLOAD, _SECRET, "v1=abc", 1_800_000_000),
        (_PAYLOAD, _SECRET, "t=soon,v1=abc", 1_800_000_000),
        (_PAYLOAD, _SECRET, "t=1800000000,v1=é", 1_800_000_000),
    ],
)
def test_verify_webhook_signature_rejects(body: bytes, secret: str, header: str, now: int) -> None:
    assert not verify_webhook_signature(secret, body, header, now=now)
