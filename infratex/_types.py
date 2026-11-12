"""Typed response objects returned by the Infratex SDK."""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional


class _Base:
    """Lightweight base that populates attributes from a dict."""

    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data
        for key, value in data.items():
            setattr(self, key, value)

    def __repr__(self) -> str:
        name = type(self).__name__
        fields = ", ".join(
            "{}={!r}".format(k, v)
            for k, v in self._data.items()
            if not k.startswith("_")
        )
        return "{}({})".format(name, fields)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
class DocumentIndex(_Base):
    id: str
    document_id: str
    filename: Optional[str]
    method: str
    status: str
    node_count: Optional[int]
    chunk_count: Optional[int]
    has_ast: bool
    has_description: bool
    processing_time_ms: Optional[int]
    processing_ms: int
    error_message: Optional[str]
    created_at: str
    updated_at: str

    def __init__(self, data: Dict[str, Any]) -> None:
        super().__init__(_coerce_index_payload(data))


class DocumentProgress(_Base):
    """Where a pending or processing document's parse is.

    ``stage`` is ``"queued"`` (waiting for a worker, also after a stopped run
    went back to the queue), ``"parsing"`` (pages being read) or
    ``"finishing"`` (every page through; the result is being stored).
    ``pages_done`` counts finished pages out of ``pages_total``, including
    pages kept from a stopped run and pages that failed. ``attempt`` is ``0``
    while waiting for the first run and goes up when a stopped run went back
    to the queue; the document fails after ``max_attempts``. ``updated_at`` is
    when it entered the queue (``queued``) or the worker's last report, at
    least every 30 seconds (``parsing`` / ``finishing``): several minutes old
    means the run has stopped.
    """

    stage: str
    pages_done: int
    pages_total: Optional[int]
    attempt: int
    max_attempts: int
    updated_at: str


class Document(_Base):
    id: str
    filename: str
    status: str
    method: str
    pipeline: Optional[str]
    page_count: Optional[int]
    processing_time_ms: Optional[int]
    error_message: Optional[str]
    markdown_size_bytes: Optional[int]
    chunk_count: Optional[int]
    index_method: Optional[str]
    collection_id: Optional[str]
    upload_time: Optional[str]
    extraction_pages: Optional[List[Dict[str, Any]]]
    indexes: Optional[List[DocumentIndex]]
    #: Set while the document is ``pending`` or ``processing``; ``None`` once it
    #: is parsed or failed (and for a moment while processing starts).
    progress: Optional[DocumentProgress]
    #: The parse engine version the document was parsed with (``"2.0"``,
    #: ``"2.5"``); ``None`` for methods without engine versions, and when the
    #: API does not send it.
    engine_version: Optional[str]
    #: The parse speed (``"standard"`` or ``"fast"``); ``None`` for methods
    #: without a speed choice, and when the API does not send it.
    speed: Optional[str]

    def __init__(self, data: Dict[str, Any]) -> None:
        super().__init__(data)
        self.indexes = [DocumentIndex(_coerce_index_payload(item)) for item in data.get("indexes", [])]
        raw_progress = data.get("progress")
        self.progress = DocumentProgress(raw_progress) if isinstance(raw_progress, dict) else None
        self.engine_version = data.get("engine_version")
        self.speed = data.get("speed")


class UploadedDocument(_Base):
    id: str
    status: str
    method: str
    filename: str
    page_count: Optional[int]
    markdown: Optional[str]
    extraction_ms: int
    collection_id: Optional[str]
    extraction_pages: Optional[List[Dict[str, Any]]]
    #: As :attr:`Document.engine_version`.
    engine_version: Optional[str]
    #: As :attr:`Document.speed`.
    speed: Optional[str]


class DocumentList(_Base):
    documents: List[Document]
    total: int

    def __init__(self, data: Dict[str, Any]) -> None:
        super().__init__(data)
        self.documents = [Document(d) for d in data.get("documents", [])]

    def __iter__(self):  # type: ignore
        return iter(self.documents)

    def __len__(self) -> int:
        return len(self.documents)


class DocumentFigure(_Base):
    """A figure cropped from a parsed PDF.

    ``bbox`` is ``[x1, y1, x2, y2]`` in PDF points (1/72 inch), origin top-left
    of the page. ``src`` matches the ``src`` of the figure block in the
    Markdown (``figures/p12-1.png``); ``name`` is its file name.
    """

    name: str
    src: str
    page: int
    index: int
    type: str
    score: float
    bbox: List[float]


class DocumentFigureList(_Base):
    document_id: str
    figures: List[DocumentFigure]

    def __init__(self, data: Dict[str, Any]) -> None:
        super().__init__(data)
        self.figures = [DocumentFigure(f) for f in data.get("figures", [])]

    def __iter__(self):  # type: ignore
        return iter(self.figures)

    def __len__(self) -> int:
        return len(self.figures)


class DocumentRegion(_Base):
    """One layout region of a page: ``bbox`` is ``[x1, y1, x2, y2]`` in pixels
    of a page image of the page's ``width`` x ``height``; ``content`` is the
    region's recognised text (tables as HTML)."""

    id: int
    label: str
    bbox: List[float]
    content: str
    page: int


class DocumentLayoutPage(_Base):
    page: int
    width: float
    height: float
    regions: List[DocumentRegion]

    def __init__(self, data: Dict[str, Any]) -> None:
        super().__init__(data)
        self.regions = [DocumentRegion(r) for r in data.get("regions", [])]


class DocumentLayout(_Base):
    """Per-page layout regions of a document parsed with ``infratex-gamma``."""

    document_id: str
    pages: List[DocumentLayoutPage]

    def __init__(self, data: Dict[str, Any]) -> None:
        super().__init__(data)
        self.pages = [DocumentLayoutPage(p) for p in data.get("pages", [])]

    def __iter__(self):  # type: ignore
        return iter(self.pages)

    def __len__(self) -> int:
        return len(self.pages)


# ---------------------------------------------------------------------------
# Parse engines
# ---------------------------------------------------------------------------
class ParseEngineVersionInfo(_Base):
    """One engine version of a parse method.

    ``status`` is ``"stable"`` or ``"beta"``; ``default`` is ``True`` for the
    version an upload without ``engine_version`` runs.
    """

    version: str
    status: str
    default: bool


class ParseEngine(_Base):
    """A parse method's engine versions and speeds."""

    method: str
    versions: List[ParseEngineVersionInfo]
    speeds: List[str]

    def __init__(self, data: Dict[str, Any]) -> None:
        super().__init__(data)
        self.versions = [ParseEngineVersionInfo(v) for v in data.get("versions") or []]
        self.speeds = list(data.get("speeds") or [])

    @property
    def default_version(self) -> Optional[str]:
        """The version an upload without ``engine_version`` runs, if any."""
        return next((v.version for v in self.versions if v.default), None)


class ParseEngines:
    """The parse methods' engine versions and speeds (``GET /api/v1/parse-engines``).

    Iterate it for one :class:`ParseEngine` per method, or look one up with
    :meth:`get`.
    """

    engines: List[ParseEngine]

    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.engines = [ParseEngine(e) for e in data]

    def get(self, method: str) -> Optional[ParseEngine]:
        """The engine of ``method`` (``"standard-ultra-2"``, ...), or ``None``."""
        return next((e for e in self.engines if e.method == method), None)

    def __iter__(self) -> Iterator[ParseEngine]:
        return iter(self.engines)

    def __len__(self) -> int:
        return len(self.engines)

    def __repr__(self) -> str:
        return "ParseEngines({!r})".format(self.engines)


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------
class Index(_Base):
    id: str
    document_id: str
    filename: Optional[str]
    method: str
    status: str
    node_count: Optional[int]
    chunk_count: Optional[int]
    has_ast: bool
    has_description: bool
    processing_time_ms: Optional[int]
    processing_ms: int
    error_message: Optional[str]
    created_at: str
    updated_at: str

    def __init__(self, data: Dict[str, Any]) -> None:
        super().__init__(_coerce_index_payload(data))


def _coerce_index_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(data)
    payload["processing_ms"] = payload.get("processing_ms") or payload.get("processing_time_ms") or 0
    return payload


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
class SearchResult(_Base):
    document_id: str
    document_name: Optional[str]
    score: float
    content: str
    title: str
    summary: str
    node_id: Optional[str]
    chunk_index: Optional[int]
    metadata: Optional[Dict[str, Any]]
    source: str


class SearchResponse(_Base):
    method: str
    query: str
    results: List[SearchResult]

    def __init__(self, data: Dict[str, Any]) -> None:
        super().__init__(data)
        self.results = [SearchResult(r) for r in data.get("results", [])]

    def __iter__(self):  # type: ignore
        return iter(self.results)

    def __len__(self) -> int:
        return len(self.results)


# ---------------------------------------------------------------------------
# Responses (SSE streaming)
# ---------------------------------------------------------------------------
class StreamEvent:
    """A single event from the SSE response stream."""

    __slots__ = ("type", "content")

    def __init__(self, type: str, content: Any) -> None:
        self.type = type
        self.content = content

    def __repr__(self) -> str:
        return "StreamEvent(type={!r}, content={!r})".format(self.type, self.content)


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------
class Collection(_Base):
    id: str
    name: str
    created_at: str


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------
class Conversation(_Base):
    id: str
    title: str
    collection_id: Optional[str]
    document_ids: List[str]
    created_at: str
    updated_at: Optional[str]
    messages: Optional[List["ConversationMessage"]]

    def __init__(self, data: Dict[str, Any]) -> None:
        super().__init__(data)
        self.document_ids = list(data.get("document_ids", []))
        raw_messages = data.get("messages")
        self.messages = (
            [ConversationMessage(message) for message in raw_messages]
            if isinstance(raw_messages, list)
            else None
        )


class ConversationMessage(_Base):
    id: str
    role: str
    content: str
    created_at: str
    metadata: Optional[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Extractions
# ---------------------------------------------------------------------------
class ExtractionRun(_Base):
    id: str
    document_id: str
    template_id: Optional[str]
    status: str
    tier: Optional[str]
    model: str
    completeness: str
    result: Optional[Dict[str, Any]]
    evidence: Optional[Dict[str, Any]]
    processing_time_ms: Optional[int]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    #: Credits the run charged (1 credit = EUR 0.005): ``0`` for a cached or
    #: failed run, ``None`` while it runs.
    credits_charged: Optional[float]
    #: Extraction engine build that computed the result.
    engine_version: Optional[str]
    #: The pipeline that ran (``"legacy"`` or ``"v2"``); ``None`` until the run
    #: finishes.
    pipeline: Optional[str]
    #: ``True`` when an identical earlier run's result was reused at no charge.
    cached: bool
    error_message: Optional[str]
    created_at: str
    updated_at: str


class ExtractionPipelineInfo(_Base):
    """One extraction pipeline. ``available`` says whether this account may
    choose it per run with ``pipeline``."""

    id: str
    label: str
    stage: str
    available: bool


class ExtractionPipelines(_Base):
    """The extraction pipelines (``GET /api/v1/extraction-pipelines``).

    ``default`` is what a run without ``pipeline`` executes.
    """

    default: str
    pipelines: List[ExtractionPipelineInfo]

    def __init__(self, data: Dict[str, Any]) -> None:
        super().__init__(data)
        self.pipelines = [ExtractionPipelineInfo(p) for p in data.get("pipelines", [])]

    def is_available(self, pipeline: str) -> bool:
        """Whether this account may choose ``pipeline`` (``"legacy"`` or ``"v2"``)."""
        return any(p.id == pipeline and p.available for p in self.pipelines)

    def __iter__(self):  # type: ignore
        return iter(self.pipelines)

    def __len__(self) -> int:
        return len(self.pipelines)


class ExtractionRunList(_Base):
    runs: List[ExtractionRun]
    total: int

    def __init__(self, data: Dict[str, Any]) -> None:
        super().__init__(data)
        self.runs = [ExtractionRun(r) for r in data.get("runs", [])]

    def __iter__(self):  # type: ignore
        return iter(self.runs)

    def __len__(self) -> int:
        return len(self.runs)


# ---------------------------------------------------------------------------
# Account & Billing
# ---------------------------------------------------------------------------
class AccountSettings(_Base):
    allow_overage: bool
    monthly_spend_cap_micros: Optional[int]
    low_balance_threshold_micros: int
    has_payment_method: bool
    #: ``"default"`` or ``"eu_only"``: where the account's requests may be processed.
    data_residency: str


class Tenant(_Base):
    id: str
    name: str
    email: Optional[str]
    credit_balance_micros: int
    is_admin: bool
    is_frozen: bool
    frozen_reason: Optional[str]
    deleted_at: Optional[str]
    created_at: str


class Account(_Base):
    tenant: Tenant

    def __init__(self, data: Dict[str, Any]) -> None:
        super().__init__(data)
        self.tenant = Tenant(data.get("tenant", {}))


class BillingTransaction(_Base):
    """One credit-ledger entry: a charge, refund, grant or top-up.

    Amounts are in micro-euros (1 credit = 5,000). A parse charge carries the
    document id in ``source_id`` and the file name and billed pages in
    ``description`` and ``metadata``.
    """

    id: str
    transaction_type: str
    status: str
    amount_micros: int
    balance_after_micros: int
    currency: str
    source_type: Optional[str]
    source_id: Optional[str]
    description: str
    created_at: str
    metadata: Optional[Dict[str, Any]]


class BillingTransactionPage(_Base):
    """A page of the credit ledger, newest first.

    Pass ``next_before`` as ``before`` to fetch the next (older) page; it is
    ``None`` on the last page.
    """

    transactions: List[BillingTransaction]
    next_before: Optional[str]

    def __init__(self, data: Dict[str, Any]) -> None:
        super().__init__(data)
        self.transactions = [BillingTransaction(t) for t in data.get("transactions", [])]
        self.next_before = data.get("next_before")

    def __iter__(self):  # type: ignore
        return iter(self.transactions)

    def __len__(self) -> int:
        return len(self.transactions)


class BillingSummary(_Base):
    balance_micros: int
    recent_transactions: List[Dict[str, Any]]
    recent_credit_transactions: List[Dict[str, Any]]
    recent_usage: List[Dict[str, Any]]
    spend_by_service: List[Dict[str, Any]]
    daily_spend: List[Dict[str, Any]]
    totals: Dict[str, Any]


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------
class Webhook(_Base):
    """A registered webhook endpoint.

    ``events`` is empty when the endpoint takes every event type. ``secret``
    is present only on the object returned by ``webhooks.create(...)``.
    """

    id: str
    url: str
    description: Optional[str]
    events: List[str]
    enabled: bool
    created_at: str
    updated_at: str
    secret: Optional[str]

    def __init__(self, data: Dict[str, Any]) -> None:
        super().__init__(data)
        self.secret = data.get("secret")


class WebhookSecret(_Base):
    """A new signing secret (``whsec_...``) returned by ``webhooks.rotate_secret(...)``."""

    secret: str


class WebhookDelivery(_Base):
    """One delivery of an event to an endpoint, with its retry state."""

    id: str
    event_id: str
    event_type: str
    status: str
    attempts: int
    last_status_code: Optional[int]
    last_error: Optional[str]
    created_at: str
    last_attempt_at: Optional[str]
    delivered_at: Optional[str]
    next_attempt_at: Optional[str]


class WebhookDeliveryList(_Base):
    """An endpoint's deliveries, newest first (kept 30 days)."""

    items: List[WebhookDelivery]

    def __init__(self, data: Dict[str, Any]) -> None:
        super().__init__(data)
        self.items = [WebhookDelivery(d) for d in data.get("items", [])]

    def __iter__(self):  # type: ignore
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)
