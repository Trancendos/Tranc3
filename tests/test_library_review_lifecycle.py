from __future__ import annotations

from src.library.knowledge_base import ArticleStatus, Library
from src.townhall.itsm import ItsmService


def test_publish_requires_town_hall_record_and_preserves_content_hash(monkeypatch, tmp_path):
    service = ItsmService(tmp_path / "townhall.db")
    monkeypatch.setattr("src.townhall.itsm.get_itsm_service", lambda: service)
    library = Library()

    article = library.create(title="Reviewed", body="Exact content", author="author")

    assert article.status is ArticleStatus.DRAFT
    published = library.publish(article.id, reviewer="reviewer")

    assert published is article
    assert article.status is ArticleStatus.PUBLISHED
    assert article.review_id
    assert article.reviewed_by == "reviewer"
    assert article.review_location == "The Town Hall"
    reviews = service.document_reviews(article.id)
    assert len(reviews) == 1
    assert reviews[0].id == article.review_id
    service.close()


def test_material_update_returns_published_article_to_draft(monkeypatch, tmp_path):
    service = ItsmService(tmp_path / "townhall.db")
    monkeypatch.setattr("src.townhall.itsm.get_itsm_service", lambda: service)
    library = Library()
    article = library.create(title="Reviewed", body="Original", author="author")
    library.publish(article.id, reviewer="reviewer")
    invalidated = []
    monkeypatch.setattr(
        "src.library.bridge.forward_delete", lambda article_id: invalidated.append(article_id)
    )

    updated = library.update(article.id, body="Changed")

    assert updated is article
    assert article.status is ArticleStatus.DRAFT
    assert article.review_id is None
    assert article.reviewed_by is None
    assert invalidated == [article.id]
    service.close()
