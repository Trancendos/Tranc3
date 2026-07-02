"""Backward-compatibility shim — canonical: Dimensional.architecture.oci_adaptive_provider"""

from Dimensional.architecture.oci_adaptive_provider import *  # noqa: F401, F403
from Dimensional.architecture.oci_adaptive_provider import (  # noqa: F401
    _S3CompatTier,
    _aws_sig4_sign,
    _default_provider,
    _oci_sign_headers,
)
