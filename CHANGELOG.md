# Changelog

**API parity.** Every release lists the API changes it covers, each with the section of the
[API docs](https://docs.infratex.io) it matches, and anything public it does not cover yet. The
Python and Node.js SDKs ship the same API changes under the same version number.

## 1.1.0 (unreleased)

### Added

- `pipeline` (`"legacy"` | `"v2"`) on `extractions.create(...)`, sent in the JSON body only when
  set (never as a query parameter). API docs: Extraction, "v2 (beta)" and the `pipeline` row of
  `POST /api/v1/documents/{id}/extractions`.
- `InvalidPipelineError` (422 `invalid_pipeline`) and `PipelineNotAvailableError`
  (422 `pipeline_not_available`), subclasses of `InfratexError`, with `allowed_pipelines`,
  `requested_pipeline` and `available_pipelines` read from the error details. API docs:
  Extraction, "v2 (beta)"; Reference, Errors (422).
- `extractions.list_pipelines()` for `GET /api/v1/extraction-pipelines`, returning
  `ExtractionPipelines` (`default`, `pipelines`, `is_available(...)`). API docs: Extraction,
  "v2 (beta)".
- `ExtractionRun.pipeline`, `credits_charged`, `engine_version` and `cached`. API docs:
  Extraction, `GET /api/v1/extractions/{run_id}`.
- `"infratex-phi"` in the `ExtractionModel` type. API docs: Extraction, "Self-hosted extraction
  (infratex-phi)".
- `extractions.create_from_file(...)` for `POST /api/v1/extractions` (parse and extract in one
  call: the run body, `method` and a server-side `wait`). API docs: Extraction,
  `POST /api/v1/extractions`.
- `wait` (0 to 300 seconds) on `extractions.get(...)`. API docs: Extraction,
  `GET /api/v1/extractions/{run_id}`.
- `idempotency_key` on `documents.upload(...)`, `documents.upload_images(...)`,
  `documents.index(...)`, `extractions.create(...)` and `extractions.create_from_file(...)`, sent
  as the `Idempotency-Key` header. API docs: Reference, "Retries and idempotency".
- `options` (`infratex-gamma` parse options, sent as one JSON object) on `documents.upload(...)`
  and `documents.upload_images(...)`. API docs: Parsing, `POST /api/v1/documents` and "Parse
  options (infratex-gamma)".
- `documents.layout(id)` for `GET /api/v1/documents/{id}/layout`, with `DocumentLayout`,
  `DocumentLayoutPage` and `DocumentRegion`. API docs: Parsing,
  `GET /api/v1/documents/{id}/layout`.
- `account.update_settings(data_residency=...)` for `PATCH /api/v1/account/settings`, and
  `AccountSettings.data_residency`. API docs: Reference, "Data processing location".
- `client.webhooks`: `create`, `list`, `get`, `update`, `delete`, `rotate_secret`, `test`,
  `list_deliveries` and `retry_delivery`, with `Webhook`, `WebhookSecret`, `WebhookDelivery` and
  `WebhookDeliveryList`. API docs: Webhooks.
- `verify_webhook_signature(secret, body, header)`, plus the `SIGNATURE_HEADER` and
  `EVENT_ID_HEADER` names. API docs: Webhooks, "Signatures".
- `Document.progress` (`DocumentProgress`: `stage` `"queued"` | `"parsing"` | `"finishing"`,
  `pages_done`, `pages_total`, `attempt`, `max_attempts`, `updated_at`), set while a document
  is `pending` or `processing` and `None` otherwise. API docs: Parsing, "Progress" (API PR #200).
- `on_progress` on `documents.wait_until_parsed(...)`: called with the document's progress each
  time it changes (stage, pages, attempt, or the worker's keepalive `updated_at`). API docs:
  Parsing, "Progress" and "When processing stalls".
- `EncryptedPDFError` (400 `encrypted_pdf`, a PDF that needs a password to open), a subclass of
  `InfratexError`, raised by uploads before any credits are held. API docs: Reference, Errors
  (400).
- `InfratexError.request_id` (the request's id, from the error body or `X-Request-ID`) and
  `InfratexError.retry_after` (the `Retry-After` header in seconds). API docs: Reference,
  "Retries and idempotency".

### Fixed

- Errors are read from the API's error envelope (`{"error": {"code", "message", "details",
  "request_id"}}`). Before, `InfratexError.code` was `None` and the message was
  `"API request failed"` for every error the API raised itself; the top-level
  `{"code", "message"}` and `{"detail": ...}` shapes are still read. A request validation error's
  list of field errors is under `details["errors"]`.
- A client built with your own `httpx_client` now sends the API key and `User-Agent` on every
  request; before, those headers were set only on the client the SDK created.

### Changed

- When a parse fails, `wait_until_parsed(...)` still raises `InfratexError` with the document's
  `error_message` (code `document_processing_failed`); the error now also carries
  `details["document_id"]`. Its timeout (`upload_timeout`) carries the document id and the last
  progress seen. API docs: Parsing, "Document status".

### Not covered yet

- The `Idempotent-Replayed: true` response header is not surfaced: a replayed response returns
  the same object as the first one.
- `GET /api/v1/usage` is reachable with an API key but is not in the public API docs yet; it
  will be added in the release that follows its documentation.

## 1.0.0 (2026-10-20)

Announced on 20 October as 0.10.0. That version number was never published: the release
shipped as 1.0.0, so PyPI goes 0.8.1, 0.9.0, 1.0.0.

### Added

- `documents.upload(...)` accepts Word `.docx` files. The file part's content type now
  follows the extension (`application/pdf`, the Word `wordprocessingml` type, or
  `application/octet-stream`) instead of always `application/pdf`.
- `infratex-gamma` parse method (layout-aware OCR, 1 credit/page).
- `table_format` (`"otsl"` | `"html"`) on `documents.upload(...)`,
  `documents.upload_images(...)` and `documents.markdown(...)`.
- `figure_descriptions` on `documents.markdown(...)`, sent only when set so servers
  without the parameter are unaffected.
- `documents.list_figures(id)` and `documents.download_figure(id, name)` for the figure
  crops of a parsed PDF, with `DocumentFigure` / `DocumentFigureList` types.
- `completeness` (`"standard"` | `"exhaustive"`) on `extractions.create(...)`, and
  `ExtractionRun.completeness`.
- `billing.list_transactions(...)` and `billing.iter_transactions(...)` for the credit
  ledger (`GET /api/v1/billing/transactions`), with `BillingTransaction` /
  `BillingTransactionPage` types.
- Test suite (pytest with a mocked HTTP transport) and mypy/ruff configuration, installed
  with `pip install -e ".[dev]"`.

### Changed

- The README parse-method table matches the current methods and credit prices.

### Fixed

- `conversations.create(...)` body typing, so the package passes `mypy --strict`.
