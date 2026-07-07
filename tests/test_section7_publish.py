"""Tests for Section7._store_and_publish()'s Library-publish failure path (src/research/section7.py)."""

import logging
from unittest.mock import patch

from src.research.section7 import ReportType, ResearchReport, Section7


def test_store_and_publish_logs_warning_when_library_create_fails(caplog):
    section7 = Section7()
    report = ResearchReport(
        report_type=ReportType.PLATFORM_HEALTH,
        title="Test Report",
        summary="A test summary",
        recommendations=["do the thing"],
    )

    with patch("src.library.knowledge_base.get_library") as mock_get_library:
        mock_get_library.return_value.create.side_effect = RuntimeError("library unavailable")
        with caplog.at_level(logging.WARNING, logger="src.research.section7"):
            section7._store_and_publish(report)

    assert report.id in section7._reports
    assert any(
        "failed to publish report" in record.message and report.id in record.message
        for record in caplog.records
    )
