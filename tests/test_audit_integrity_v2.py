"""Portable checks for the Observatory's new, full-event hash envelope."""
import importlib.util
from pathlib import Path

import pytest

MOD = Path(__file__).resolve().parents[1] / 'workers' / 'audit-service' / 'audit_integrity.py'

def _module():
    spec = importlib.util.spec_from_file_location('observatory_audit_integrity', MOD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

@pytest.fixture
def sample():
    return dict(
        prev_hash='0' * 64,
        event_id='5c71c64f-99c0-43ee-abd6-47af85332d34',
        timestamp='2026-10-23T10:00:00+00:00',
        service='the-observatory',
        action='audit.write',
        actor='service:tests',
        resource='resource-1',
        outcome='success',
        severity='info',
        details_json='{"trace_id":"trace-1", "payload":{"z":2,"a":1}}',
    )

def test_v2_hash_is_stable_and_64_lowercase_hex(sample):
    h = _module().compute_v2_hash(**sample)
    assert len(h) == 64
    assert all(ch in '0123456789abcdef' for ch in h)
    assert h == _module().compute_v2_hash(**sample)

def test_v2_hash_covers_severity_and_details(sample):
    f = _module().compute_v2_hash
    original = f(**sample)
    assert f(**{**sample, 'severity': 'critical'}) != original
    assert f(**{**sample, 'details_json': '{"trace_id":"trace-2", "payload":{"z":2,"a":1}}'}) != original

def test_v2_hash_covers_previous_link_and_every_core_field(sample):
    f = _module().compute_v2_hash
    original = f(**sample)
    for field in ('prev_hash', 'event_id', 'timestamp', 'service', 'action', 'actor', 'resource', 'outcome'):
        assert f(**{**sample, field: str(sample[field]) + 'x'}) != original, field

def test_v2_hash_canonicalises_json_key_order(sample):
    f = _module().compute_v2_hash
    original = f(**sample)
    reordered = '{"payload": {"a":1,"z":2}, "trace_id":"trace-1"}'
    assert f(**{**sample, 'details_json': reordered}) == original

def test_v2_hash_rejects_invalid_nonfinite_and_nonobject_details(sample):
    f = _module().compute_v2_hash
    for bad in ('not-json', '[1,2]', '{"value": NaN}'):
        with pytest.raises((ValueError, TypeError)):
            f(**{**sample, 'details_json': bad})

def test_v2_hash_is_not_legacy_v1_hash(sample):
    import hashlib
    old_fields = ('prev_hash', 'event_id', 'timestamp', 'service', 'action', 'actor', 'resource', 'outcome')
    legacy = hashlib.sha256('|'.join(sample[k] for k in old_fields).encode()).hexdigest()
    assert _module().compute_v2_hash(**sample) != legacy
