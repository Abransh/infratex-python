"""Documents resource."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Sequence, Union, overload

from .._http import InfratexError
from .._types import DocumentList, Document, Index, UploadedDocument

if TYPE_CHECKING:
    from .._http import HTTPClient

ParseMethod = Literal["standard", "max", "standard-ultra-2", "infratex-phi"]
IndexMethod = Literal["vector", "hybrid"]

_PARSED_STATES = {"parsed", "indexed", "done"}


class Documents:
    """Interact with the ``/api/v1/documents`` endpoints."""

    _poll_interval_seconds = 1.0

    def __init__(self, client: HTTPClient) -> None:
        self._client = client

    @overload
    def upload(
        self,
        file_path: str,
        *,
        method: Optional[ParseMethod] = None,
        collection_id: Optional[str] = None,
        wait: Literal[True] = True,
    ) -> UploadedDocument: ...

    @overload
    def upload(
        self,
        file_path: str,
        *,
        method: Optional[ParseMethod] = None,
        collection_id: Optional[str] = None,
        wait: Literal[False],
    ) -> Document: ...

    def upload(
        self,
        file_path: str,
        *,
        method: Optional[ParseMethod] = None,
        collection_id: Optional[str] = None,
        wait: bool = True,
    ) -> Union[Document, UploadedDocument]:
        """Upload and parse a PDF document.

        Parameters
        ----------
        file_path:
            Local path to the PDF file.
        method:
            Parsing method. One of ``"standard"`` (1 credit/page),
            ``"max"`` (3), ``"infratex-phi"`` (3), or ``"standard-ultra-2"`` (3).
            Defaults to ``"standard"`` server-side.
        collection_id:
            Optional collection to assign the document to.
        wait:
            When ``True`` (default), poll until parsing is complete and return
            the final markdown-bearing document payload. When ``False``,
            return the queued document resource immediately.
        """
        filename = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            files = {"file": (filename, f, "application/pdf")}
            data: Dict[str, Any] = {}
            if method is not None:
                data["method"] = method
            if collection_id is not None:
                data["collection_id"] = collection_id

            resp = self._client.request(
                "POST",
                "/api/v1/documents",
                data=data,
                files=files,
            )
        created = Document(resp)
        if not wait:
            return created
        return self._wait_for_uploaded_document(created.id)

    @overload
    def upload_images(
        self,
        file_paths: Sequence[str],
        *,
        method: Optional[ParseMethod] = None,
        collection_id: Optional[str] = None,
        wait: Literal[True] = True,
    ) -> UploadedDocument: ...

    @overload
    def upload_images(
        self,
        file_paths: Sequence[str],
        *,
        method: Optional[ParseMethod] = None,
        collection_id: Optional[str] = None,
        wait: Literal[False],
    ) -> Document: ...

    def upload_images(
        self,
        file_paths: Sequence[str],
        *,
        method: Optional[ParseMethod] = None,
        collection_id: Optional[str] = None,
        wait: bool = True,
    ) -> Union[Document, UploadedDocument]:
        """Upload and parse an ordered batch of page images.

        Parameters
        ----------
        file_paths:
            Ordered local paths to PNG, JPEG, or WebP image files. The order of
            the files is treated as the page order of the document.
        method:
            Parsing method: ``"standard"``, ``"max"``, ``"infratex-phi"``, or
            ``"standard-ultra-2"``. Defaults to ``"standard"``.
        collection_id:
            Optional collection to assign the document to.
        wait:
            When ``True`` (default), poll until parsing is complete and return
            the final markdown-bearing document payload. When ``False``,
            return the queued document resource immediately.
        """
        paths = list(file_paths)
        if not paths:
            raise ValueError("file_paths must contain at least one image path")

        data: Dict[str, Any] = {}
        if method is not None:
            data["method"] = method
        if collection_id is not None:
            data["collection_id"] = collection_id

        files: List[tuple[str, tuple[str, Any, str]]] = []
        handles = []
        try:
            for file_path in paths:
                filename = os.path.basename(file_path)
                handle = open(file_path, "rb")
                handles.append(handle)
                mime_type = _guess_image_mime_type(filename)
                files.append(("files", (filename, handle, mime_type)))

            resp = self._client.request(
                "POST",
                "/api/v1/documents/images",
                data=data,
                files=files,
            )
        finally:
            for handle in handles:
                handle.close()

        created = Document(resp)
        if not wait:
            return created
        return self._wait_for_uploaded_document(created.id)

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        collection_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> DocumentList:
        """List documents.

        Parameters
        ----------
        limit:
            Maximum number of documents to return.
        offset:
            Pagination offset.
        collection_id:
            Filter by collection.
        status:
            Filter by document status.
        """
        params: Dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "collection_id": collection_id,
            "status": status,
        }
        resp = self._client.request("GET", "/api/v1/documents", params=params)
        return DocumentList(resp)

    @overload
    def get(self, document_id: str, *, wait: Literal[False] = False) -> Document: ...

    @overload
    def get(self, document_id: str, *, wait: Literal[True]) -> UploadedDocument: ...

    def get(self, document_id: str, *, wait: bool = False) -> Union[Document, UploadedDocument]:
        """Retrieve a single document by ID.

        When ``wait=True``, poll until parsing completes and return the
        markdown-bearing :class:`UploadedDocument`.
        """
        if wait:
            return self._wait_for_uploaded_document(document_id)
        resp = self._client.request("GET", "/api/v1/documents/{}".format(document_id))
        return Document(resp)

    def markdown(self, document_id: str) -> str:
        """Download the parsed markdown for a document."""
        return self._client.request_text("GET", "/api/v1/documents/{}/markdown".format(document_id))

    def update(
        self,
        document_id: str,
        *,
        filename: Optional[str] = None,
        collection_id: Optional[str] = None,
        remove_collection: bool = False,
    ) -> Document:
        """Rename a document or change its collection assignment.

        Pass ``filename`` to rename, ``collection_id`` to move the document into
        a collection, or ``remove_collection=True`` to detach it from its
        current collection.
        """
        if collection_id is not None and remove_collection:
            raise ValueError("collection_id and remove_collection cannot be used together")

        body: Dict[str, Any] = {}
        if filename is not None:
            body["filename"] = filename
        if collection_id is not None:
            body["collection_id"] = collection_id
        if remove_collection:
            body["remove_collection"] = True

        if not body:
            raise ValueError("update requires filename, collection_id, or remove_collection")

        resp = self._client.request(
            "PATCH",
            "/api/v1/documents/{}".format(document_id),
            json_body=body,
        )
        return Document(resp)

    def wait_until_parsed(self, document_id: str) -> UploadedDocument:
        """Block until the document finishes parsing and return its markdown payload."""
        return self._wait_for_uploaded_document(document_id)

    def _wait_for_uploaded_document(self, document_id: str) -> UploadedDocument:
        deadline = time.monotonic() + self._client.timeout_seconds

        while True:
            document = self.get(document_id, wait=False)
            if document.status in _PARSED_STATES:
                return UploadedDocument(
                    {
                        "id": document.id,
                        "status": document.status,
                        "method": document.method,
                        "filename": document.filename,
                        "page_count": document.page_count,
                        "markdown": self.markdown(document_id),
                        "extraction_ms": document.processing_time_ms or 0,
                        "collection_id": document.collection_id,
                        "extraction_pages": document.extraction_pages,
                    }
                )
            if document.status == "error":
                raise InfratexError(
                    document.error_message or "Document processing failed",
                    status_code=409,
                    code="document_processing_failed",
                )
            if time.monotonic() >= deadline:
                raise InfratexError(
                    "Document processing timed out",
                    status_code=504,
                    code="upload_timeout",
                )
            time.sleep(self._poll_interval_seconds)

    def delete(self, document_id: str) -> None:
        """Delete a document."""
        self._client.request_no_content("DELETE", "/api/v1/documents/{}".format(document_id))

    def index(
        self,
        document_id: str,
        *,
        method: IndexMethod = "vector",
        wait: bool = True,
    ) -> Index:
        """Create a search index for a document.

        Parameters
        ----------
        document_id:
            The document to index.
        method:
            Indexing strategy: ``"vector"`` or ``"hybrid"``.
        wait:
            When ``True`` (default), poll until the index reaches ``indexed``.
        """
        resp = self._client.request(
            "POST",
            "/api/v1/documents/{}/indexes".format(document_id),
            json_body={"method": method},
        )
        created = Index(resp)
        if not wait:
            return created
        return self.wait_until_indexed(document_id, method=method)

    def list_indexes(self, document_id: str) -> List[Index]:
        """List index resources for a document."""
        resp = self._client.request("GET", "/api/v1/documents/{}/indexes".format(document_id))
        return [Index(index) for index in resp]

    def get_index(
        self,
        document_id: str,
        method: IndexMethod,
        *,
        wait: bool = False,
    ) -> Index:
        """Retrieve a single index resource for a document."""
        if not wait:
            resp = self._client.request(
                "GET",
                "/api/v1/documents/{}/indexes/{}".format(document_id, method),
            )
            return Index(resp)
        return self.wait_until_indexed(document_id, method=method)

    def wait_until_indexed(self, document_id: str, *, method: IndexMethod = "vector") -> Index:
        """Block until the method-specific index reaches ``indexed``."""
        deadline = time.monotonic() + self._client.timeout_seconds

        while True:
            index = self.get_index(document_id, method, wait=False)
            if index.status == "indexed":
                return index
            if index.status == "error":
                raise InfratexError(
                    index.error_message or "Indexing failed",
                    status_code=409,
                    code="index_failed",
                )
            if time.monotonic() >= deadline:
                raise InfratexError(
                    "Indexing timed out",
                    status_code=504,
                    code="index_timeout",
                )
            time.sleep(self._poll_interval_seconds)


def _guess_image_mime_type(file_path: str) -> str:
    lower = file_path.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".webp"):
        return "image/webp"
    return "application/octet-stream"
