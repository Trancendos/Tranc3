"""The Library — Pydantic models"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentFormat(str, Enum):
    markdown = "markdown"
    html = "html"
    plain = "plain"


class LibraryBackend(str, Enum):
    outline = "outline"
    bookstack = "bookstack"
    wikijs = "wikijs"
    gollum = "gollum"
    dokuwiki = "dokuwiki"
    mkdocs = "mkdocs"
    gitea = "gitea"
    tiddlywiki = "tiddlywiki"
    offline = "offline"


class DocumentCreate(BaseModel):
    title: str
    content: str
    format: DocumentFormat = DocumentFormat.markdown
    collection: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentResponse(BaseModel):
    doc_id: str
    title: str
    content: str
    format: DocumentFormat
    collection: Optional[str]
    tags: List[str]
    metadata: Dict[str, Any]
    backend: LibraryBackend
    url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    collection: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)
    format: Optional[DocumentFormat] = None


class SearchResult(BaseModel):
    doc_id: str
    title: str
    excerpt: str
    collection: Optional[str]
    url: Optional[str]
    backend: LibraryBackend
    score: Optional[float] = None


class SearchResponse(BaseModel):
    results: List[SearchResult]
    total: int
    backend: LibraryBackend


class BackendStatus(BaseModel):
    name: LibraryBackend
    healthy: bool
    pheromone: float
    calls_in_window: int
    quota_remaining: int


class LibraryStatus(BaseModel):
    active_backend: LibraryBackend
    backends: List[BackendStatus]
