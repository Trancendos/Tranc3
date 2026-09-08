from scripts.documentation_health import (
    DocumentContract,
    render_catalog,
    source_changes_missing_canonical_updates,
    unlisted_wiki_pages,
    validate_contracts,
)


def contract(**overrides):
    values = {
        "identifier": "deployment",
        "title": "Deployment",
        "canonical": "docs/deployment.md",
        "kind": "how-to",
        "owner": "Platform",
        "source_paths": ("compose.yml",),
    }
    values.update(overrides)
    return DocumentContract(**values)


def test_changed_source_requires_canonical_document_update():
    errors = source_changes_missing_canonical_updates([contract()], ["compose.yml"])

    assert errors == [
        "deployment source changed without reviewing canonical document docs/deployment.md"
    ]


def test_changed_source_accepts_canonical_document_update():
    errors = source_changes_missing_canonical_updates(
        [contract()], ["compose.yml", "docs/deployment.md"]
    )

    assert errors == []


def test_sidebar_check_reports_unlisted_pages(tmp_path):
    (tmp_path / "Home.md").write_text("# Home\n", encoding="utf-8")
    (tmp_path / "Unlisted.md").write_text("# Unlisted\n", encoding="utf-8")
    sidebar = tmp_path / "_Sidebar.md"
    sidebar.write_text("[Home](Home)\n", encoding="utf-8")

    assert unlisted_wiki_pages(sidebar) == ["Unlisted"]


def test_validation_rejects_missing_paths_and_invalid_kinds(tmp_path):
    errors = validate_contracts([contract(kind="memo")], root=tmp_path)

    assert "deployment uses invalid documentation kind 'memo'" in errors
    assert "deployment references missing path: docs/deployment.md" in errors
    assert "deployment references missing path: compose.yml" in errors


def test_catalog_explains_human_review_boundary():
    catalog = render_catalog([contract()])

    assert "does not autonomously alter operational or security guidance" in catalog
