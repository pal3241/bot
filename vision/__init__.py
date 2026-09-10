"""SENA vision/expression event subsystem.

The package deliberately keeps camera/CV backends optional.  Backends produce
normalised observations; the engine converts them into semantic events that the
Discord expression layer can consume.
"""

from .engine import ExpressionEvent, ExpressionEventEngine, VisionObservation

__all__ = ["ExpressionEvent", "ExpressionEventEngine", "VisionObservation"]
