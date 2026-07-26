"""Working out what a layer's axes are, in order of how much the answer is worth."""

from __future__ import annotations

import numpy as np
import pytest

from skop_napari import _axes


class FakeDims:
    def __init__(self, displayed=(), current_step=()):
        self.displayed = displayed
        self.current_step = current_step


class FakeViewer:
    def __init__(self, displayed=(), current_step=(), layers=()):
        self.dims = FakeDims(displayed, current_step)
        self.layers = list(layers)


class FakeLayer:
    """Just the layer attributes resolution reads."""

    def __init__(self, data, *, metadata=None, axis_labels=None, rgb=False):
        self.data = data
        self.metadata = dict(metadata or {})
        self.axis_labels = axis_labels
        self.rgb = rgb


# -- rung 1: somebody already answered ------------------------------------


def test_metadata_outranks_everything():
    data = np.zeros((5, 4, 6))
    layer = FakeLayer(data, metadata={_axes.METADATA_KEY: ("lifetime", "y", "x")})
    guess = _axes.resolve(data, layer)
    assert guess.axes == ("lifetime", "y", "x")
    assert guess.declared


def test_metadata_may_have_been_written_as_a_string():
    data = np.zeros((3, 4))
    layer = FakeLayer(data, metadata={_axes.METADATA_KEY: "y x"})
    assert _axes.resolve(data, layer).axes == ("y", "x")


def test_a_resolution_is_written_back_to_the_layer():
    # The point of the exercise: guess once per layer, not once per run.
    layer = FakeLayer(np.zeros((4, 4)))
    _axes.remember(layer, ("y", "x"))
    assert layer.metadata[_axes.METADATA_KEY] == ("y", "x")


# -- rung 2: the data or its provenance says -------------------------------


def test_xarray_dims_are_taken_at_their_word():
    xr = pytest.importorskip("xarray")
    data = xr.DataArray(np.zeros((5, 4, 6)), dims=("pln", "row", "col"))
    guess = _axes.resolve(data)
    assert guess.axes == ("pln", "row", "col")
    assert guess.declared
    # skop resolves the synonyms; this layer does not second-guess them.


def test_ngff_axes_are_read_from_layer_metadata():
    data = np.zeros((2, 5, 4, 6))
    layer = FakeLayer(
        data,
        metadata={
            "multiscales": [
                {
                    "axes": [
                        {"name": "t", "type": "time"},
                        {"name": "z", "type": "space"},
                        {"name": "y", "type": "space"},
                        {"name": "x", "type": "space"},
                    ]
                }
            ]
        },
    )
    assert _axes.resolve(data, layer).axes == ("t", "z", "y", "x")


def test_metadata_that_does_not_fit_the_array_is_ignored():
    # Stale labels from another array must not be applied to this one.
    data = np.zeros((4, 6))
    layer = FakeLayer(data, metadata={_axes.METADATA_KEY: ("z", "y", "x")})
    guess = _axes.resolve(data, layer)
    assert guess.axes == ("y", "x")
    assert not guess.declared


# -- rung 3: napari's own layer state --------------------------------------


def test_layer_axis_labels_are_used_when_they_are_real():
    data = np.zeros((5, 4, 6))
    layer = FakeLayer(data, axis_labels=("depth", "row", "col"))
    guess = _axes.resolve(data, layer)
    assert guess.axes == ("depth", "row", "col")
    assert guess.declared


def test_naparis_placeholder_labels_are_not_axis_names():
    # napari fills unlabelled axes with '-3', '-2', '-1'. Reading those as
    # names would produce three axes called minus-something.
    data = np.zeros((5, 4, 6))
    layer = FakeLayer(data, axis_labels=("-3", "-2", "-1"))
    guess = _axes.resolve(data, layer)
    assert guess.axes == ("z", "y", "x")
    assert not guess.declared


def test_rgb_settles_a_trailing_channel_axis():
    data = np.zeros((4, 6, 3))
    layer = FakeLayer(data, axis_labels=("row", "col", "-1"), rgb=True)
    assert _axes.resolve(data, layer).axes == ("row", "col", "c")


# -- rung 4: convention ----------------------------------------------------


def test_a_plane_is_yx():
    guess = _axes.resolve(np.zeros((4, 6)))
    assert guess.axes == ("y", "x")
    assert not guess.declared


def test_a_stack_is_zyx():
    assert _axes.resolve(np.zeros((5, 4, 6))).axes == ("z", "y", "x")


def test_a_trailing_extent_of_three_is_rgb():
    assert _axes.resolve(np.zeros((4, 6, 3))).axes == ("y", "x", "c")


def test_the_viewer_decides_which_axes_are_the_plane():
    # The displayed axes are a fact about the viewer, not a guess -- even
    # though which of the others is z remains one.
    data = np.zeros((5, 4, 6))
    viewer = FakeViewer(displayed=(0, 1))
    guess = _axes.resolve(data, None, viewer)
    assert guess.axes == ("y", "x", "z")
    assert "viewer layout" in guess.source


def test_a_displayed_trailing_axis_is_spatial_not_rgb():
    # A (4, 6, 3) volume being shown as x=3 is genuinely three planes wide;
    # calling it RGB would transpose the image out from under the user.
    data = np.zeros((4, 6, 3))
    viewer = FakeViewer(displayed=(1, 2))
    assert _axes.resolve(data, None, viewer).axes == ("z", "y", "x")


def test_convention_never_invents_a_channel_axis():
    # The hazard this avoids: every image op declares Axes.pack("yxc?"), so a
    # guessed c is *consumed* as a channel rather than iterated over. Guessing
    # t wrongly only ever changes what the iteration is called.
    for ndim in (4, 5, 6):
        axes = _axes.resolve(np.zeros((2,) * ndim)).axes
        assert "c" not in axes, axes
    assert _axes.resolve(np.zeros((2, 3, 4, 5))).axes == ("t", "z", "y", "x")
    assert _axes.resolve(np.zeros((2, 3, 4, 5, 6))).axes == ("dim0", "t", "z", "y", "x")


# -- odds and ends ---------------------------------------------------------


def test_labels_may_be_typed_with_spaces_or_commas():
    assert _axes.parse(" z, y ,x ") == ("z", "y", "x")
    assert _axes.parse("lifetime y x") == ("lifetime", "y", "x")
    assert _axes.parse("   ") == ()


def test_the_layer_is_found_from_the_data_the_combo_handed_over():
    # napari's ImageData annotation drops the layer and keeps only its array,
    # and the array is the one thing that identifies it again.
    data = np.zeros((4, 4))
    layer = FakeLayer(data)
    viewer = FakeViewer(layers=[FakeLayer(np.ones((4, 4))), layer])
    assert _axes.layer_for(viewer, data) is layer
    assert _axes.layer_for(viewer, np.zeros((4, 4))) is None
    assert _axes.layer_for(None, data) is None


def test_slider_positions_are_reported_per_axis_name():
    # This is what makes "the current Z slice" mean the one being looked at.
    viewer = FakeViewer(current_step=(7, 0, 0))
    assert _axes.positions(("z", "y", "x"), viewer) == {"z": 7, "y": 0, "x": 0}
    # A viewer that has not caught up with this array says nothing at all.
    assert _axes.positions(("z", "y", "x"), FakeViewer(current_step=(0, 0))) == {}
