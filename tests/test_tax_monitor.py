# tests/test_tax_monitor.py
"""Guards against stale VAT constants in src/monetisation/billing.py.TaxMonitor.

UK_VAT_THRESHOLD_GBP was hardcoded at the pre-2024 £85,000 figure long after
HMRC raised it to £90,000 (effective 2024-04-01); EU_VAT_RATES["FI"] was
similarly stale after Finland's 2024-09-01 rate rise. Both were confirmed
stale by direct review before being fixed — this test pins the corrected
values so they can't silently regress."""

from __future__ import annotations

from src.monetisation.billing import TaxMonitor


def test_uk_vat_threshold_matches_current_hmrc_limit():
    assert TaxMonitor.UK_VAT_THRESHOLD_GBP == 90_000


def test_finland_vat_rate_matches_2024_increase():
    assert TaxMonitor.EU_VAT_RATES["FI"] == 0.255


def test_romania_vat_rate_matches_2025_increase():
    assert TaxMonitor.EU_VAT_RATES["RO"] == 0.21


def test_slovakia_vat_rate_matches_2025_increase():
    assert TaxMonitor.EU_VAT_RATES["SK"] == 0.23


def test_below_threshold_uk_sale_charges_no_vat():
    monitor = TaxMonitor()
    record = monitor.record_sale(amount_gbp=100.0, country_code="GB")
    assert record["vat_treatment"] == "below_threshold"
    assert record["vat_amount_gbp"] == 0.0


def test_above_threshold_uk_sale_charges_standard_rate():
    monitor = TaxMonitor()
    monitor.record_sale(amount_gbp=TaxMonitor.UK_VAT_THRESHOLD_GBP, country_code="GB")
    record = monitor.record_sale(amount_gbp=100.0, country_code="GB")
    assert record["vat_treatment"] == "uk_vat"
    assert record["vat_amount_gbp"] == 20.0


def test_eu_sale_uses_country_specific_rate():
    monitor = TaxMonitor()
    record = monitor.record_sale(amount_gbp=100.0, country_code="FI")
    assert record["vat_treatment"] == "eu_oss_FI"
    assert record["vat_amount_gbp"] == 25.5
