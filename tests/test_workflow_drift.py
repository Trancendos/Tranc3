from scripts import check_workflow_drift


def test_compare_reads_utf8_workflows_on_windows(monkeypatch, tmp_path):
    github_directory = tmp_path / "github"
    forgejo_directory = tmp_path / "forgejo"
    github_directory.mkdir()
    forgejo_directory.mkdir()
    workflow = "name: 🌐\njobs: {}\n"
    (github_directory / "unicode.yml").write_text(workflow, encoding="utf-8")
    (forgejo_directory / "unicode.yml").write_text(workflow, encoding="utf-8")
    monkeypatch.setattr(check_workflow_drift, "GH_DIR", github_directory)
    monkeypatch.setattr(check_workflow_drift, "FJ_DIR", forgejo_directory)

    assert check_workflow_drift.compare("unicode.yml") == []
