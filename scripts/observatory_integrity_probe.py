#!/usr/bin/env python3
"""Read-only, zero-dependency Observatory integrity probe.

Exit 0: healthy. Exit 1: audit integrity failure/incomplete response.
Exit 2: unavailable/transport failure. Never modifies or heals audit records.
Can be called by systemd timers, cron, or an external supervisor.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener


def validate_base_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('Provide only a base URL without credentials, query, or path')
    if not parsed.hostname or parsed.scheme not in ('http', 'https'):
        raise ValueError('An HTTP(S) URL with a hostname is required')
    if parsed.scheme == 'http' and parsed.hostname not in ('127.0.0.1', '::1', 'localhost'):
        raise ValueError('HTTP is only permitted for loopback; remote endpoints require HTTPS')
    return url.rstrip('/')


class _RefuseRedirect(HTTPRedirectHandler):
    """Never forward a credential-bearing request to a redirected endpoint."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, 'Redirect refused', headers, fp)


def fetch_json(url: str, *, timeout: float = 5, secret: str | None = None) -> dict:
    headers = {'Accept': 'application/json'}
    if secret:
        headers['X-Internal-Secret'] = secret
    req = Request(url, headers=headers)
    with build_opener(_RefuseRedirect()).open(req, timeout=timeout) as response:  # nosec B310: URL scheme validated by check()
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError('Endpoint returned an unexpected non-object payload')
    return payload


def classify(health: dict, verification: dict) -> dict:
    checked = verification.get('checked')
    total = health.get('total_events')
    counts_plausible = (type(checked) is int and checked >= 0 and
                        (type(total) is not int or checked >= total))
    safe = (health.get('status') == 'healthy' and health.get('chain_valid') is True
            and verification.get('valid') is True and counts_plausible)
    return {'state': 'healthy' if safe else 'critical', 'code': 0 if safe else 1,
            'chain_valid': bool(health.get('chain_valid') is True and verification.get('valid') is True),
            'verified_events': verification.get('checked') if isinstance(verification.get('checked'), int) else None}


def check(base_url: str, *, timeout: float = 5, secret: str | None = None) -> dict:
    base = validate_base_url(base_url)
    try:
        health = fetch_json(base + '/health', timeout=timeout, secret=secret)
        verify = fetch_json(base + '/verify', timeout=timeout, secret=secret)
        result = classify(health, verify)
    except (ValueError, OSError, TimeoutError, json.JSONDecodeError):
        # Do not write raw error messages: they may contain the URL or headers.
        result = {'state': 'unavailable', 'code': 2, 'chain_valid': None, 'verified_events': None}
    return {'event': 'observatory.integrity_probe', 'at': datetime.now(timezone.utc).isoformat(), **result}


def main() -> int:
    parser = argparse.ArgumentParser(description='Read-only Observatory audit integrity probe')
    parser.add_argument('--url', default='http://127.0.0.1:8025')
    parser.add_argument('--timeout', type=float, default=5)
    args = parser.parse_args()
    try:
        result = check(args.url, timeout=args.timeout, secret=os.getenv('INTERNAL_SECRET'))
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return result['code']


if __name__ == '__main__':
    raise SystemExit(main())
