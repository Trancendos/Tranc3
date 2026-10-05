"""Backward-compatibility shim — canonical: Dimensionals.architecture.oci_adaptive_provider"""

from Dimensionals.architecture.oci_adaptive_provider import *  # noqa: F401, F403
from Dimensionals.architecture.oci_adaptive_provider import (  # noqa: F401
    _aws_sig4_sign,
    _default_provider,
    _oci_sign_headers,
    _S3CompatTier,
)
