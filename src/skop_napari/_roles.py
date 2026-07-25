"""Translating skop's roles into napari's vocabulary.

This is the whole of what makes skop-napari napari-specific: two lookup
tables. Everything else in this package is about widgets and threads.

skop deliberately refuses to guess -- an unannotated array reports no role at
all -- so the guessing happens here, where there is a viewer to guess for.
"""

from __future__ import annotations

from typing import Any

import napari.types as nt
import numpy as np

from skop import OutputSpec, ParamSpec, Role

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
