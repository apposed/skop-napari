"""Working out what a layer's axes actually are.

skop refuses to guess this ([skop design
0005](https://github.com/apposed/scikit-ops/blob/main/docs/design/0005-dimensional-adaptation.md)),
and it is right to: guessing needs a viewer to guess *for*. This module is
that guess, and it is the whole reason skop-napari can hand a `(z, y, x)`
stack to a strictly 2-D op.

The rungs run from "someone said so" to "it has three dimensions, so probably".
Each answer carries where it came from and whether it was declared or inferred,
because the panel shows both -- a user who disagrees with rung four types over
it, and what they type is written back onto the layer, so the disagreement is
had once rather than every run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: napari fills unlabelled axes with their own index, as '-3', '-2', '-1'.
#: Those are placeholders, not names, and must not be read as axis labels.
_PLACEHOLDER = re.compile(r"^-?\d+$")

#: Where skop-napari stashes a resolved or user-edited answer, so that later
#: runs -- and other plugins -- can read it back.
METADATA_KEY = "skop_axes"

#: Names for axes that convention, rather than anybody's declaration, has to
#: fill in, innermost last: one spare axis is z, two are t and z.
#:
#: Note what is *not* here: c. Convention may only invent axis names that no
#: op consumes, and c is the one canonical axis ops routinely declare as
#: optional -- `Axes("y", "x", "c?")` is every image op in the collection.
#: Guess c wrongly and a timepoint axis lands in the channel slot, where
#: `to_gray` averages over it instead of iterating; guess t wrongly and the
#: worst case is that the op iterates over something the user would have
#: called z, which computes exactly the same thing. A trailing RGB extent is
#: the sole way c gets inferred, and that reads a real property of the data.
#:
#: skop now enforces the same rule from its side -- an optional slot is filled
#: by a name match and never by position ([skop design 0006]) -- so a wrong
#: guess here is caught twice rather than once.
_CONVENTIONAL = ("t", "z")


@dataclass(frozen=True)
class AxisGuess:
    """What this layer's axes are, and how much that is worth."""

    axes: tuple[str, ...]
    #: Human-readable provenance, shown in the panel.
    source: str
    #: Whether someone declared this, as opposed to it being inferred from
    #: shape and viewer layout. The panel shows inferred answers differently;
    #: it does not refuse to use them, since an op that iterates over an
    #: unknown axis does the same thing whatever that axis turns out to be.
    declared: bool

    def __str__(self) -> str:
        return " ".join(self.axes)


def parse(text: str) -> tuple[str, ...]:
    """Read axis labels a human typed, as whitespace- or comma-separated."""
    return tuple(part for part in re.split(r"[,\s]+", text.strip()) if part)


def layer_for(viewer: Any, data: Any) -> Any:
    """Find the layer a magicgui layer combo took *data* from.

    napari's ``ImageData`` annotation hands an op the layer's ``.data`` and
    drops the layer itself, which is exactly the object holding the axis
    metadata. The choice stored that same array, so identity finds it again.

    Returns None when there is no match -- no viewer, or a value that came
    from somewhere else -- and resolution simply falls through to convention.
    """
    if viewer is None or data is None:
        return None
    for layer in getattr(viewer, "layers", ()):
        if layer.data is data:
            return layer
    return None


def resolve(data: Any, layer: Any = None, viewer: Any = None) -> AxisGuess:
    """Work out the axes of *data*, best evidence first.

    Args:
        data: The array itself, which may be an xarray carrying its own dims.
        layer: The napari layer it came from, if known.
        viewer: The viewer, for the axes it is currently displaying.

    Returns:
        Always an answer. The last rung is pure convention, and says so.
    """
    ndim = len(getattr(data, "shape", ()) or ())
    for rung in (_from_metadata, _from_xarray, _from_ngff, _from_layer_labels):
        found = rung(data, layer)
        if found is not None and len(found.axes) == ndim:
            return found
    return _by_convention(data, layer, viewer, ndim)


def remember(layer: Any, axes: tuple[str, ...]) -> None:
    """Write a resolution back onto the layer.

    The point of the exercise: inference gets *better* over a session rather
    than being redone identically every run, and a correction a user made once
    stays made.
    """
    if layer is not None:
        layer.metadata[METADATA_KEY] = tuple(axes)


def positions(axes: tuple[str, ...], viewer: Any) -> dict[str, int]:
    """Where the viewer's sliders currently sit, per axis name.

    This is what makes "run on the current Z slice" mean the slice the user is
    actually looking at, rather than slice zero.
    """
    steps = getattr(getattr(viewer, "dims", None), "current_step", ())
    if len(steps) != len(axes):
        return {}
    return {axis: int(step) for axis, step in zip(axes, steps)}


# -- the rungs -----------------------------------------------------------


def _from_metadata(data: Any, layer: Any) -> AxisGuess | None:
    """Rung 1: somebody already answered this, here or in an earlier run."""
    stored = getattr(layer, "metadata", {}).get(METADATA_KEY) if layer else None
    if not stored:
        return None
    axes = parse(stored) if isinstance(stored, str) else tuple(str(a) for a in stored)
    return AxisGuess(axes, "layer metadata", declared=True)


def _from_xarray(data: Any, layer: Any) -> AxisGuess | None:
    """Rung 2a: the array brought its own dimension names."""
    dims = getattr(data, "dims", None)
    if not isinstance(dims, tuple) or not all(isinstance(d, str) for d in dims):
        return None
    return AxisGuess(dims, "array dims", declared=True)


def _from_ngff(data: Any, layer: Any) -> AxisGuess | None:
    """Rung 2b: OME-NGFF wrote the axes into the layer's metadata."""
    multiscales = getattr(layer, "metadata", {}).get("multiscales") if layer else None
    try:
        entries = multiscales[0]["axes"]
    except (TypeError, LookupError):
        return None
    names = tuple(
        entry["name"] if isinstance(entry, dict) else str(entry) for entry in entries
    )
    return AxisGuess(names, "NGFF metadata", declared=True) if names else None


def _from_layer_labels(data: Any, layer: Any) -> AxisGuess | None:
    """Rung 3: the layer's own axis labels, and its RGB flag.

    ``rgb`` is the one piece of napari layer state that is decisive rather
    than suggestive: napari only sets it for a trailing channel axis.
    """
    if layer is None:
        return None
    labels = getattr(layer, "axis_labels", None) or ()
    named = [
        None if not str(label).strip() or _PLACEHOLDER.match(str(label)) else str(label)
        for label in labels
    ]
    if getattr(layer, "rgb", False) and named:
        named[-1] = named[-1] or "c"
    if not named or any(name is None for name in named):
        return None
    return AxisGuess(tuple(named), "layer axis labels", declared=True)


def _by_convention(data: Any, layer: Any, viewer: Any, ndim: int) -> AxisGuess:
    """Rung 4: shape and viewer layout, which is convention, not evidence.

    Two things are worth more than they look. A trailing extent of 3 or 4 is
    taken as RGB, matching what ``skop.ops._util.to_gray`` already assumes.
    And when a viewer is displaying the data, *which* axes form the visible
    plane is a fact rather than a guess -- it just does not say whether the
    remaining slider is z or t, which is exactly the distinction that does not
    matter to an op about to iterate over it.
    """
    shape = tuple(getattr(data, "shape", ()) or ())
    axes: list[str | None] = [None] * ndim
    source = "shape"

    if ndim >= 3 and shape[-1] in (3, 4) and not _spatially_displayed(viewer, ndim - 1):
        axes[-1] = "c"

    plane = _displayed(viewer, ndim)
    if plane is not None:
        source = "shape and viewer layout"
    else:
        plane = tuple(i for i in range(ndim) if axes[i] is None)[-2:]
    for name, index in zip(("y", "x"), plane):
        axes[index] = name

    spare = [i for i, name in enumerate(axes) if name is None]
    for name, index in zip(_names_for(len(spare)), spare):
        axes[index] = name

    return AxisGuess(
        tuple(name or "?" for name in axes),
        source,
        declared=False,
    )


def _names_for(count: int) -> list[str]:
    """Names for *count* spare axes, innermost last.

    Beyond what convention covers, axes get positional names rather than
    invented meanings. ``dim0`` satisfies no op's declaration, so such an axis
    is always iterated or rejected -- never silently consumed as something it
    is not.
    """
    if count <= len(_CONVENTIONAL):
        return list(_CONVENTIONAL[-count:]) if count else []
    extra = count - len(_CONVENTIONAL)
    return [f"dim{i}" for i in range(extra)] + list(_CONVENTIONAL)


def _displayed(viewer: Any, ndim: int) -> tuple[int, ...] | None:
    """The two axes the viewer is showing as a plane, if it is showing any."""
    dims = getattr(viewer, "dims", None)
    shown = getattr(dims, "displayed", None)
    if not shown or len(shown) != 2 or max(shown) >= ndim:
        # 3-D rendering, or a viewer whose dimensionality has not caught up
        # with this layer; either way there is no plane to read off.
        return None
    return tuple(int(i) for i in shown)


def _spatially_displayed(viewer: Any, axis: int) -> bool:
    """Whether the viewer is showing *axis* as part of the plane.

    A trailing extent of 3 is RGB far more often than not -- but if the viewer
    is displaying that axis, it is spatial, and calling it a channel would
    transpose the image out from under the user.
    """
    shown = getattr(getattr(viewer, "dims", None), "displayed", None) or ()
    return axis in tuple(int(i) for i in shown)
