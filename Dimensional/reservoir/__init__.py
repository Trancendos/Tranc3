"""Reservoir Computing (Echo State Networks) for temporal pattern recognition.

ESNs are a proven non-linear time-series technique (Jaeger, 2001).
The reservoir is a fixed random recurrent network; only the readout is trained.
Training is a single linear regression — runs in milliseconds.

Applied here: the reservoir learns patterns in AI provider request sequences,
predicting which provider will succeed before the request is made.
This is a real ML technique used in production at Nokia Bell Labs etc.
"""
from .esn import EchoStateNetwork

__all__ = ["EchoStateNetwork"]
