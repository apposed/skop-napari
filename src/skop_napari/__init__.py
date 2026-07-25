"""Run scikit-ops ops from napari.

Exposes one widget, the Ops panel, which lists every op skop can discover and
runs the chosen one in its own Appose environment -- off the GUI thread, with
progress and cancellation, and with its outputs added to the viewer as the
layer types their roles call for.
"""

from __future__ import annotations

from ._panel import OpsPanel

__all__ = ["OpsPanel"]
