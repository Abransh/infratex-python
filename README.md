# Infratex Python SDK

Official Python client for the [Infratex](https://infratex.io) document intelligence API. Parse PDFs, Word documents, or ordered image batches, build search indexes, retrieve cited context, stream grounded answers, and extract structured fields.

## Installation

```bash
pip install infratex
```

## Quick start

```python
from infratex import Infratex

client = Infratex(api_key="infratex_sk_...")

# Upload and parse a PDF (waits for parsing by default)
doc = client.documents.upload("report.pdf", method="standard")
print(doc.id, doc.status, doc.page_count)

# Index for retrieval, then wait until it's ready
client.documents.index(doc.id, method="hybrid")

# Stream a cited answer
for event in client.responses.create(
    message="Summarize the key findings with citations.",
    method="hybrid",
    model="fast",
    document_ids=[doc.id],
):
    if event.type == "sources":
        print("Sources:", event.content)
    elif event.type == "text":
        print(event.content, end="")
```

## Authentication

Pass your API key directly or set the `INFRATEX_API_KEY` environment variable. Use a
server-side key (`infratex_sk_...`); keep it out of browser code.

```python
# Explicit
client = Infratex(api_key="infratex_sk_...")

# From environment
import os
os.environ["INFRATEX_API_KEY"] = "infratex_sk_..."
client = Infratex()
```

## Parse methods

| Method | Credits / page | Notes |
|--------|----------------|-------|
| `standard` | 1 | Default. Fast, high-quality Markdown for most documents. |
| `max` | 3 | Figures are marked, captioned, and described. For documents where charts, diagrams, and photos carry meaning. |
| `infratex-phi` | 3 | Proprietary in-house model. Dense tables, financial statements, faithfulness-first OCR. |
| `infratex-gamma` | 1 | Layout-aware OCR. Faithful text and tables at volume, with a bounding box for every region. |
| `standard-ultra-2` | 3 | High-fidelity vision for complex nested tables and chart-heavy reports (API-only). |

Both `documents.upload(...)` and `documents.upload_images(...)` accept any of these
methods and default to `standard`. A method that is temporarily unavailable is rejected
at upload with `InfratexError` (status 503, code `method_unavailable`).

`table_format` (`"otsl"` or `"html"`) sets the table syntax the parser emits; it is
honoured by `max`, `infratex-phi`, `infratex-gamma` and `standard-ultra-2` (`standard`
returns Markdown pipe tables). It is stored with the document: a document parsed as
`otsl` can be read back as either syntax with `documents.markdown(id, table_format=...)`,
one parsed as `html` only as HTML.

`documents.upload(...)` also accepts a Word `.docx`. It is read from the file itself (no
model call) and billed at the `standard` price whatever `method` you send; the document
reports `standard` as its method. Legacy `.doc` and macro-enabled `.docm` files are
rejected with status 415.

## Resources

### Documents

```python
# Upload a PDF — waits for parsing and returns the markdown-bearing document.
doc = client.documents.upload("report.pdf")
doc = client.documents.upload("report.pdf", method="max", collection_id="col-id")

# Word documents use the same call.
doc = client.documents.upload("contract.docx")

# Table syntax: "otsl" (default) or "html". Stored with the document, not changeable later.
doc = client.documents.upload("report.pdf", method="infratex-gamma", table_format="otsl")

# Upload an ordered image batch as document pages (file order = page order).
images = client.documents.upload_images(["page-1.png", "page-2.png"], method="standard")

# Queue-first if you want to manage the parse lifecycle yourself.
queued = client.documents.upload("report.pdf", wait=False)
doc = client.documents.wait_until_parsed(queued.id)   # or: client.documents.get(queued.id, wait=True)

# List / get / markdown
docs = client.documents.list(limit=50, offset=0, collection_id="col-id")
print(docs.total)
doc = client.documents.get("doc-id")
md = client.documents.markdown("doc-id")
md = client.documents.markdown("doc-id", table_format="html")   # OTSL tables as <table>

# Rename or move between collections
client.documents.update("doc-id", filename="q3-report.pdf")
client.documents.update("doc-id", collection_id="col-id")
client.documents.update("doc-id", remove_collection=True)

# Delete
client.documents.delete("doc-id")

# Index — waits until the method-specific index reaches "indexed".
client.documents.index("doc-id", method="hybrid")

# Queue-first indexing if you want to manage polling yourself.
client.documents.index("doc-id", method="hybrid", wait=False)
indexes = client.documents.list_indexes("doc-id")
index = client.documents.wait_until_indexed("doc-id", method="hybrid")
```

### Searches

Retrieve cited context without generating text. Send one scope: `document_ids` **or**
`collection_id`.

```python
results = client.searches.create(
    query="Find indemnity carve-outs",
    method="hybrid",
    limit=5,
    document_ids=["doc-id"],
)
for hit in results:
    print(hit.document_name, hit.score, hit.content[:160])
```

### Responses (streaming)

Stream answers grounded in indexed documents. Events arrive in order: `sources`,
`thinking` (only when `reasoning=True`), `text` deltas, then `done`.

```python
for event in client.responses.create(
    message="What are the top risks?",
    method="hybrid",
    model="fast",       # "fast" (default) or "pro"
    collection_id="col-id",
    limit=8,
    reasoning=False,
):
    if event.type == "sources":
        sources = event.content
    elif event.type == "text":
        print(event.content, end="")
    elif event.type == "done":
        print("\n--- done ---")
```

```python
# Managed multi-turn thread with persisted scope
conv = client.conversations.create(title="Quarterly Analysis", collection_id="col-id")

for event in client.responses.create(
    message="How does that compare with the previous quarter?",
    method="hybrid",
    model="pro",
    conversation_id=conv.id,   # scope comes from the conversation; omit document_ids/collection_id
):
    if event.type == "text":
        print(event.content, end="")
```

### Extractions

Extract structured fields from a parsed document. Provide inline field definitions, or
reference a `template_id` created in the dashboard — exactly one is required.

```python
run = client.extractions.create(
    "doc-id",
    model="fast",              # "fast" (default) or "pro"
    include_evidence=True,
    inline_fields=[
        {"name": "counterparty", "type": "string", "description": "Legal name of the counterparty"},
        {"name": "effective_date", "type": "date", "description": "Contract effective date"},
        {"name": "termination_fee", "type": "number", "description": "Any explicit termination fee"},
    ],
)

result = client.extractions.wait_until_done(run.id, include_evidence=True)
print(result.result)     # {"counterparty": "...", "effective_date": "...", ...}
print(result.evidence)   # per-field evidence (present because include_evidence=True)

# Reference a dashboard-managed template instead of inline fields
run = client.extractions.create("doc-id", template_id="tpl-id")

# List prior runs, then export tabular results
runs = client.extractions.list("doc-id")
export = client.extractions.export(run.id, format="xlsx")   # or "csv"
export.save("results.xlsx")
```

Field definitions support nested shapes: `type` may be `string`, `number`, `integer`,
`boolean`, `date`, `enum`, `object`, or `array`. Use `enum_values` for `enum`,
`properties` (a list of fields) for `object`, and `items` (a single field) for `array`.
Extraction templates are created and managed in the dashboard.

### Collections

```python
col = client.collections.create(name="Q3 Reports")
cols = client.collections.list()
col = client.collections.get("col-id")
client.collections.update("col-id", name="Q4 Reports")
client.collections.delete("col-id")
```

### Conversations

```python
conv = client.conversations.create(title="Analysis", collection_id="col-id")
convs = client.conversations.list()
conv = client.conversations.get("conv-id")   # includes messages
client.conversations.delete("conv-id")
```

### Account & Billing

```python
account = client.account.get()
print(account.tenant["email"], account.tenant["credit_balance_micros"])

settings = client.account.settings()
print(settings.allow_overage, settings.monthly_spend_cap_micros)

billing = client.billing.get()
print(billing.balance_micros)
```

## Error handling

```python
from infratex import Infratex, InfratexError

client = Infratex(api_key="infratex_sk_...")

try:
    doc = client.documents.get("nonexistent-id")
except InfratexError as e:
    print(e.status_code)  # 404
    print(e.code)         # error code from the API
    print(str(e))         # human-readable message
```

## Configuration

```python
client = Infratex(
    api_key="infratex_sk_...",
    base_url="https://api.infratex.io",  # custom base URL
    timeout=300.0,                        # request / poll timeout in seconds
)

# Use as a context manager
with Infratex(api_key="infratex_sk_...") as client:
    doc = client.documents.upload("report.pdf")
```

## License

MIT
