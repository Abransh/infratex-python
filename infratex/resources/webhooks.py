"""Webhooks resource: endpoints that receive signed events when work finishes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Sequence

from .._types import Webhook, WebhookDelivery, WebhookDeliveryList, WebhookSecret

if TYPE_CHECKING:
    from .._http import HTTPClient

WebhookEvent = Literal[
    "document.parsed",
    "document.failed",
    "index.completed",
    "index.failed",
    "extraction.completed",
    "extraction.failed",
]
DeliveryStatus = Literal["pending", "delivered", "failed"]

MAX_DELIVERY_PAGE = 100


class Webhooks:
    """Interact with the ``/api/v1/webhooks`` endpoints.

    Infratex POSTs a signed JSON event to each enabled endpoint when a parse,
    an index build or an extraction run finishes or fails. Verify each
    delivery with :func:`infratex.verify_webhook_signature`.
    """

    def __init__(self, client: HTTPClient) -> None:
        self._client = client

    def create(
        self,
        *,
        url: str,
        events: Optional[Sequence[WebhookEvent]] = None,
        description: Optional[str] = None,
    ) -> Webhook:
        """Register a public HTTPS endpoint (up to 10 per account).

        ``events`` empty or omitted sends every event type. The returned
        webhook carries the signing ``secret``, shown only here and on
        :meth:`rotate_secret`: store it.
        """
        body: Dict[str, Any] = {"url": url}
        if events is not None:
            body["events"] = list(events)
        if description is not None:
            body["description"] = description
        resp = self._client.request("POST", "/api/v1/webhooks", json_body=body)
        return Webhook(resp)

    def list(self) -> List[Webhook]:
        """List the account's endpoints (without secrets)."""
        resp = self._client.request("GET", "/api/v1/webhooks")
        return [Webhook(w) for w in resp]

    def get(self, webhook_id: str) -> Webhook:
        """Retrieve one endpoint (without its secret)."""
        resp = self._client.request("GET", "/api/v1/webhooks/{}".format(webhook_id))
        return Webhook(resp)

    def update(
        self,
        webhook_id: str,
        *,
        url: Optional[str] = None,
        events: Optional[Sequence[WebhookEvent]] = None,
        description: Optional[str] = None,
        enabled: Optional[bool] = None,
        clear_description: bool = False,
    ) -> Webhook:
        """Change an endpoint. Only the arguments given are sent.

        ``events=[]`` makes it take every event type; ``clear_description=True``
        removes its description; ``enabled=False`` pauses deliveries.
        """
        if description is not None and clear_description:
            raise ValueError("description and clear_description cannot be used together")

        body: Dict[str, Any] = {}
        if url is not None:
            body["url"] = url
        if events is not None:
            body["events"] = list(events)
        if description is not None:
            body["description"] = description
        if clear_description:
            body["description"] = None
        if enabled is not None:
            body["enabled"] = enabled

        if not body:
            raise ValueError(
                "update requires url, events, description, enabled, or clear_description"
            )

        resp = self._client.request(
            "PATCH", "/api/v1/webhooks/{}".format(webhook_id), json_body=body
        )
        return Webhook(resp)

    def delete(self, webhook_id: str) -> None:
        """Remove an endpoint and its delivery log."""
        self._client.request_no_content("DELETE", "/api/v1/webhooks/{}".format(webhook_id))

    def rotate_secret(self, webhook_id: str) -> WebhookSecret:
        """Issue a new signing secret; deliveries from now on are signed with it."""
        resp = self._client.request(
            "POST", "/api/v1/webhooks/{}/rotate-secret".format(webhook_id)
        )
        return WebhookSecret(resp)

    def test(self, webhook_id: str) -> WebhookDelivery:
        """Queue a ``webhook.test`` event to the endpoint (60 an hour per account)."""
        resp = self._client.request("POST", "/api/v1/webhooks/{}/test".format(webhook_id))
        return WebhookDelivery(resp)

    def list_deliveries(
        self,
        webhook_id: str,
        *,
        status: Optional[DeliveryStatus] = None,
        limit: Optional[int] = None,
    ) -> WebhookDeliveryList:
        """The endpoint's deliveries, newest first, kept 30 days.

        ``limit`` is 1 to 100 (server default 50).
        """
        if limit is not None and not 1 <= limit <= MAX_DELIVERY_PAGE:
            raise ValueError("limit must be between 1 and {}".format(MAX_DELIVERY_PAGE))
        resp = self._client.request(
            "GET",
            "/api/v1/webhooks/{}/deliveries".format(webhook_id),
            params={"status": status, "limit": limit},
        )
        return WebhookDeliveryList(resp)

    def retry_delivery(self, webhook_id: str, delivery_id: str) -> WebhookDelivery:
        """Send a failed or delivered delivery again, with the same event id and body.

        The API answers 409 ``delivery_pending`` while it is still being retried
        (120 retries an hour per account).
        """
        resp = self._client.request(
            "POST",
            "/api/v1/webhooks/{}/deliveries/{}/retry".format(webhook_id, delivery_id),
        )
        return WebhookDelivery(resp)
