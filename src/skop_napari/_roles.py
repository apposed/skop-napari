"""Translating skop's roles into napari's vocabulary.

This is the whole of what makes skop-napari napari-specific: two lookup
tables and one shape adapter. Everything else in this package is about
widgets and threads.

skop deliberately refuses to guess -- an unannotated array reports no role at
all -- so the guessing happens here, where there is a viewer to guess for.

The adapter exists because a role names what an array *means*, not how napari
wants it laid out. skop states bounding boxes as ``(N, 4)`` rows of
``[min_y, min_x, max_y, max_x]``; napari reads that same array as a single
shape with N vertices in four dimensions. Reconciling the two is this
package's job, not skop's -- skop.types imports no GUI, and the layout napari
wants is not more correct, only more napari.
"""

from __future__ import annotations

from typing import Any

import napari.types as nt
import numpy as np

from skop import OutputSpec, ParamSpec, Role, boxes

# What magicgui should build an input widget for. The napari.types aliases
# give a layer combo box that hands the op the layer's .data, which is the
# ndarray the op wanted in the first place.
_INPUT_TYPES: dict[Role, Any] = {
    Role.image: nt.ImageData,
    Role.labels: nt.LabelsData,
    Role.points: nt.PointsData,
    Role.shapes: nt.ShapesData,
    Role.surface: nt.SurfaceData,
    Role.tracks: nt.TracksData,
    Role.vectors: nt.VectorsData,
}

# What kind of layer an output becomes, as Layer.create() names them.
_LAYER_TYPES: dict[Role, str] = {
    Role.image: "image",
    Role.labels: "labels",
    Role.points: "points",
    Role.shapes: "shapes",
    Role.surface: "surface",
    Role.tracks: "tracks",
    Role.vectors: "vectors",
}


def annotation_for(param: ParamSpec) -> Any:
    """The type magicgui should build a widget for, given an op parameter."""
    if param.role is not None:
        return _INPUT_TYPES[param.role]
    if param.type is np.ndarray:
        # An unannotated array is most likely a picture, and offering the
        # wrong layer combo beats offering no way to pass one at all.
        return nt.ImageData
    return param.type


def layer_type_for(output: OutputSpec) -> str | None:
    """The napari layer type for an op output, or None if it is not a layer.

    Scalars -- unseg's nucleus and cell counts, say -- have no layer to be,
    and belong in a results panel instead.
    """
    if output.role is not None:
        return _LAYER_TYPES[output.role]
    if output.type is np.ndarray:
        return "image"
    return None


def layer_args_for(output: OutputSpec, value: Any) -> tuple[Any, dict[str, Any]]:
    """The data and extra layer keywords for an op output.

    Returns the value unchanged for every role whose layout napari already
    agrees with, which is all of them but one.

    Bounding boxes are the exception. skop states them as ``(N, 4)`` rows of
    ``[min_y, min_x, max_y, max_x]`` -- see ``skop.boxes`` -- and a Shapes
    layer handed that array reads it as one N-vertex shape in 4-D and raises.
    ``skop.boxes.to_napari`` reshapes it into the ``(N, 2, 2)`` corner pairs a
    rectangle wants, but only with ``shape_type`` said out loud: napari's
    default for a 2-vertex shape is a rectangle that then complains it was
    given two corners rather than four.
    """
    if output.role is Role.shapes:
        array = np.asarray(value)
        if array.ndim == 2 and array.shape[-1] == 4:
            return boxes.to_napari(array), {
                "shape_type": "rectangle",
                # A Shapes layer defaults to solid white faces, which would
                # cover the very thing the boxes are pointing at.
                "face_color": "transparent",
                "edge_color": "yellow",
                "edge_width": 2,
            }
    return value, {}
