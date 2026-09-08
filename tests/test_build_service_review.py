from scripts.build_service_review import first_difference


def test_first_difference_names_nested_changed_value():
    expected = {"services": [{"checks": {"entity_mapped": {"detail": "claimed"}}}]}
    actual = {"services": [{"checks": {"entity_mapped": {"detail": "unclaimed"}}}]}

    assert first_difference(expected, actual) == (
        "<root>.services[0].checks.entity_mapped.detail: expected 'claimed', got 'unclaimed'"
    )


def test_first_difference_names_missing_key():
    assert (
        first_difference({"services": []}, {}) == "<root>.services: missing from generated review"
    )
