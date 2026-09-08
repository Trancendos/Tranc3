from scripts import build_service_review


def test_scan_imports_uses_posix_paths_in_generated_data(tmp_path, monkeypatch):
    context = tmp_path / "workers" / "example"
    context.mkdir(parents=True)
    (context / "worker.py").write_text(
        "from Dimensional.service_auth_fastapi import require_internal\n"
    )
    monkeypatch.setattr(build_service_review, "ROOT", tmp_path)

    imports = build_service_review.scan_imports(context)

    assert imports["unguarded"] == ["workers/example/worker.py:1 Dimensional.service_auth_fastapi"]


def test_first_difference_names_nested_changed_value():
    expected = {"services": [{"checks": {"entity_mapped": {"detail": "claimed"}}}]}
    actual = {"services": [{"checks": {"entity_mapped": {"detail": "unclaimed"}}}]}

    assert build_service_review.first_difference(expected, actual) == (
        "<root>.services[0].checks.entity_mapped.detail: expected 'claimed', got 'unclaimed'"
    )


def test_first_difference_names_missing_key():
    assert (
        build_service_review.first_difference({"services": []}, {})
        == "<root>.services: missing from generated review"
    )
