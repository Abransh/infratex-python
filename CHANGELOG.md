# Changelog

## 1.0.0

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
