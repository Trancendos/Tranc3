"""Backward-compatibility shim — canonical: Dimensional.architecture.oci_adaptive_provider"""

from Dimensional.architecture.oci_adaptive_provider import *  # noqa: F401, F403
from Dimensional.architecture.oci_adaptive_provider import (  # noqa: F401
    _aws_sig4_sign,
    _default_provider,
    _oci_sign_headers,
    _S3CompatTier,
)
