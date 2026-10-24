"""Independent regression tests for remote VRAR3D asset ingestion."""

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'workers' / 'vrar3d'))
from asset_ingest import AssetIngestError, fetch_asset_bytes, validate_asset_url


@pytest.fixture(autouse=True)
def resolved_public_ip(monkeypatch):
    monkeypatch.setattr('asset_ingest.socket.getaddrinfo', lambda *args, **kwargs: [
        (2, 1, 6, '', ('93.184.215.14', 443))
    ])


@pytest.mark.parametrize('url', [
    'http://assets.example.org/model.glb',
    'https://127.0.0.1/model.glb',
    'https://assets.example.org:8443/model.glb',
    'https://user:password@assets.example.org/model.glb',
    'https://other.example.org/model.glb',
    'https://assets.example.org\\@127.0.0.1/model.glb',
])
def test_rejects_untrusted_urls(url):
    with pytest.raises(AssetIngestError):
        validate_asset_url(url, frozenset({'assets.example.org'}))


def test_rejects_private_dns(monkeypatch):
    monkeypatch.setattr('asset_ingest.socket.getaddrinfo', lambda *args, **kwargs: [
        (2, 1, 6, '', ('10.0.0.1', 443))
    ])
    with pytest.raises(AssetIngestError, match='non-public'):
        validate_asset_url('https://assets.example.org/model.glb', frozenset({'assets.example.org'}))


def test_rejects_mixed_public_private_dns(monkeypatch):
    monkeypatch.setattr('asset_ingest.socket.getaddrinfo', lambda *args, **kwargs: [
        (2, 1, 6, '', ('93.184.215.14', 443)),
        (2, 1, 6, '', ('169.254.169.254', 443)),
    ])
    with pytest.raises(AssetIngestError, match='non-public'):
        validate_asset_url('https://assets.example.org/model.glb', frozenset({'assets.example.org'}))


@pytest.mark.asyncio
async def test_valid_streamed_asset():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b'glb-bytes'))
    data = await fetch_asset_bytes('https://assets.example.org/a.glb',
        allowed_hosts=frozenset({'assets.example.org'}), transport=transport)
    assert data == b'glb-bytes'


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [301, 302, 307, 403, 500])
async def test_rejects_redirects_and_errors(status):
    transport = httpx.MockTransport(lambda req: httpx.Response(status, headers={'Location': 'http://127.0.0.1/private'}))
    with pytest.raises(AssetIngestError, match='HTTP'):
        await fetch_asset_bytes('https://assets.example.org/a.glb',
            allowed_hosts=frozenset({'assets.example.org'}), transport=transport)


@pytest.mark.asyncio
async def test_rejects_oversized_content_length():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, headers={'Content-Length': '120'}, content=b'x' * 120))
    with pytest.raises(AssetIngestError, match='size limit'):
        await fetch_asset_bytes('https://assets.example.org/a.glb',
            allowed_hosts=frozenset({'assets.example.org'}), max_bytes=64, transport=transport)


@pytest.mark.asyncio
async def test_rejects_oversized_chunked_content():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b'x' * 65))
    with pytest.raises(AssetIngestError, match='size limit'):
        await fetch_asset_bytes('https://assets.example.org/a.glb',
            allowed_hosts=frozenset({'assets.example.org'}), max_bytes=64, transport=transport)


@pytest.mark.asyncio
async def test_rejects_empty_asset():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b''))
    with pytest.raises(AssetIngestError, match='empty'):
        await fetch_asset_bytes('https://assets.example.org/a.glb',
            allowed_hosts=frozenset({'assets.example.org'}), transport=transport)
