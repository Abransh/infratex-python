"""Webhook signature verification."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Dict, List, Optional, Union

__all__ = ["verify_webhook_signature", "SIGNATURE_HEADER", "EVENT_ID_HEADER"]

#: Header carrying ``t=<unix seconds>,v1=<hex HMAC-SHA256>``.
SIGNATURE_HEADER = "Infratex-Signature"
#: Header carrying the event id, the same on every retry: deduplicate on it.
EVENT_ID_HEADER = "Infratex-Event-Id"

DEFAULT_TOLERANCE_SECONDS = 300


def verify_webhook_signature(
    secret: str,
    body: Union[bytes, str],
    header: str,
    *,
    tolerance: int = DEFAULT_TOLERANCE_SECONDS,
    now: Optional[int] = None,
) -> bool:
    """Whether ``header`` is a valid, recent ``Infratex-Signature`` of ``body``.

    Pass the raw request body exactly as received (before any JSON parsing)
    and the endpoint's ``whsec_...`` secret. The digest is compared in
    constant time, and a timestamp more than ``tolerance`` seconds from
    ``now`` (default: the current time) is rejected, so a captured delivery
    cannot be replayed later.
    """
    raw = body.encode() if isinstance(body, str) else body
    fields: Dict[str, List[str]] = {}
    for part in header.split(","):
        name, _, value = part.strip().partition("=")
        fields.setdefault(name, []).append(value)
    try:
        timestamp = int(fields["t"][0])
    except (KeyError, ValueError):
        return False
    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > tolerance:
        return False
    expected = hmac.new(
        secret.encode(), "{}.".format(timestamp).encode() + raw, hashlib.sha256
    ).hexdigest()
    return any(
        candidate.isascii() and hmac.compare_digest(expected, candidate)
        for candidate in fields.get("v1", [])
    )
