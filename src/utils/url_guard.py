"""One scheme check for outbound URLs, instead of five copies and four omissions.

``urllib.request.urlopen`` handles more than HTTP. Its default opener carries a
``FileHandler``, so a URL that reaches it from configuration can be ``file:///etc/passwd``
and the call succeeds -- it reads a local file and returns it as a response body. The
same is true of ``ftp://`` and, where installed, ``data:``. That is why bandit's B310
exists, and it is why "the URL comes from our own config" is not on its own an answer:
config is an operator-supplied string, and an operator-supplied string that selects the
*scheme* selects which protocol handler runs.

This estate already believed that. Five call sites (``layer_rotator``,
``meilisearch_client``, ``web_scraper``, ``misp_connector``, ``security_checks``) each
carried their own inline ``if parsed.scheme not in ("http", "https")`` before the
urlopen. Four did not: the vLLM and llama.cpp providers, the two zero-cost provider
probes, and the SHI roadmap advisor, all of which build their URL from an environment
variable. The pyproject B310 justification nonetheless claimed no in-scope call site
lets a caller choose the scheme -- an overclaim cubic caught on PR #1207.

Rather than narrow the sentence, the four were brought up to what the other five
already did, through this one function so there is a single definition to read and a
single place to change. ``tests/test_url_scheme_guard.py`` holds the claim to the code.
"""

from __future__ import annotations

from typing import Iterable
from urllib.parse import urlparse

ALLOWED_SCHEMES: tuple[str, ...] = ("http", "https")


class UnsafeURLScheme(ValueError):
    """Raised when a URL's scheme is outside the allowed set.

    Subclasses `ValueError` so a caller that already handles malformed-URL
    errors handles this too, rather than needing to learn a new exception to
    stay correct.
    """


def require_http_url(url: str, *, allowed: Iterable[str] = ALLOWED_SCHEMES) -> str:
    """Return ``url`` unchanged if its scheme is allowed; raise otherwise.

    Raising rather than returning False is deliberate: every caller here is about to
    perform a network call, and a silent False at the top of a ``try/except Exception``
    would be indistinguishable from "the service is down" -- which is precisely the
    failure mode that let the unguarded sites sit unnoticed.
    """
    allowed_set = tuple(allowed)
    scheme = urlparse(url).scheme.lower()
    if scheme not in allowed_set:
        raise UnsafeURLScheme(
            f"refusing to open URL with scheme {scheme!r}; allowed: {', '.join(allowed_set)}"
        )
    return url


def is_http_url(url: str, *, allowed: Iterable[str] = ALLOWED_SCHEMES) -> bool:
    """Boolean form, for probes whose contract is already 'is this reachable?'.

    Catches `ValueError` as well as `UnsafeURLScheme`, because `urlparse` raises
    it directly on a malformed bracketed host -- `http://[::1` and friends -- and
    that happens *before* any scheme check can run. Letting it escape turned a
    typo in one provider's URL into an exception out of provider discovery,
    taking down the discovery of every other provider with it. A malformed URL is
    an unavailable provider, which is exactly what this function is for saying.
    """
    try:
        require_http_url(url, allowed=allowed)
    except (UnsafeURLScheme, ValueError):
        return False
    return True
