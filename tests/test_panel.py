"""The Ops panel, against a real napari viewer.

These tests run ops for real, in their own Appose environments, so they need
the 'minimal' environment built. That is the cheapest one skop has -- python
plus numpy plus appose -- and building it once makes the difference between
testing the plumbing and testing a mock of it.
"""

from __future__ import annotations

import numpy as np
import pytest

from skop_napari import OpsPanel


@pytest.fixture
def panel(make_napari_viewer, qtbot):
    viewer = make_napari_viewer()
    widget = OpsPanel(viewer)
    viewer.window.add_dock_widget(widget)
    yield widget
    # Each panel holds its own Runner, and so its own worker processes.
    widget._runner.close()


def _choose(panel, function_name):
    label = next(
        lbl for lbl, spec in panel._by_label.items() if spec.function == function_name
    )
    panel._picker.value = label


def test_lists_the_collection(panel):
    functions = {spec.function for spec in panel._by_label.values()}
    assert {"otsu", "stardist2d", "unseg", "add"} <= functions


def test_choosing_an_op_rebuilds_the_inputs(panel):
    _choose(panel, "otsu")
    assert [w.name for w in panel._inputs.widgets] == [
        "image",
        "invert",
        "label_objects",
    ]

    _choose(panel, "add")
    assert [w.name for w in panel._inputs.widgets] == ["a", "b"]
    assert "Environment: minimal" in panel._notes.value


def test_image_inputs_offer_the_viewers_layers(panel, make_napari_viewer):
    viewer = panel._viewer
    viewer.add_image(np.zeros((16, 16), dtype=np.uint8), name="first")
    viewer.add_image(np.ones((16, 16), dtype=np.uint8), name="second")

    _choose(panel, "otsu")
    image = next(w for w in panel._inputs.widgets if w.name == "image")
    # The role annotation is what turned this into a layer combo box. It
    # offers the layers' data, not the layers, which is what the op wants.
    assert len(image.choices) == 2
    assert [float(choice.mean()) for choice in image.choices] == [0.0, 1.0]


def test_a_layer_added_later_shows_up_in_the_combo(panel):
    _choose(panel, "otsu")
    image = next(w for w in panel._inputs.widgets if w.name == "image")
    assert image.choices == ()

    # napari refreshes the choices of the widgets it docks, so an op panel
    # built before the user opened an image still offers it.
    panel._viewer.add_image(np.zeros((4, 4), dtype=np.uint8), name="later")
    assert len(image.choices) == 1


def test_running_an_op_adds_its_output_as_the_right_layer_type(panel, qtbot):
    viewer = panel._viewer
    viewer.add_image(np.zeros((8, 8), dtype=np.uint16), name="blank")
    _choose(panel, "find_nothing")
    # The sole image layer is already selected: a combo built with choices
    # present picks the first one, which is what a user would have to do.
    image = next(w for w in panel._inputs.widgets if w.name == "image")
    assert image.value is viewer.layers["blank"].data

    with qtbot.waitSignal(panel.finished, timeout=300_000):
        panel._start()

    kinds = {layer.name: type(layer).__name__ for layer in viewer.layers}
    # labels -> Labels and points -> Points, from the op's role annotations.
    assert kinds["labels [find_nothing]"] == "Labels"
    assert kinds["points [find_nothing]"] == "Points"


def test_scalar_outputs_go_to_the_results_panel(panel, qtbot):
    _choose(panel, "add")
    next(w for w in panel._inputs.widgets if w.name == "a").value = 17
    next(w for w in panel._inputs.widgets if w.name == "b").value = 25

    with qtbot.waitSignal(panel.finished, timeout=300_000):
        panel._start()

    # NB: assert on contents, not on .visible -- a magicgui widget reports
    # the Qt state, and the test viewer is never actually shown.
    assert [(w.name, w.value) for w in panel._results] == [("result", "42")]
    # A scalar has no layer to be, so nothing was added to the viewer.
    assert len(panel._viewer.layers) == 0


def test_progress_reaches_the_panel_and_cancel_stops_the_op(panel, qtbot):
    panel._viewer.add_image(np.ones((10, 10), dtype=np.float32), name="ones")
    _choose(panel, "slow_sum")
    next(w for w in panel._inputs.widgets if w.name == "steps").value = 60

    with qtbot.waitSignal(panel.finished, timeout=300_000):
        panel._start()
        # Progress is reported from the worker process, relayed by an Appose
        # listener thread, and must arrive on the GUI thread to be shown.
        qtbot.waitUntil(
            lambda: "Summing chunk" in (panel._progress.label or ""),
            timeout=120_000,
        )
        assert panel._run is not None
        panel._stop()

    # slow_sum polls cancel_requested() and returns its partial sum, so a
    # canceled op still delivers -- 100.0 is what a full run would total.
    total = float(panel._results[0].value)
    assert 0.0 < total < 100.0


def test_a_failing_op_reports_rather_than_raises(panel, qtbot):
    # No image layer exists, so scale gets None and fails in the worker.
    _choose(panel, "scale")
    assert next(w for w in panel._inputs.widgets if w.name == "image").value is None

    with qtbot.waitSignal(panel.finished, timeout=300_000):
        panel._start()

    assert [w.name for w in panel._results] == ["error"]
    assert "TaskException" in panel._results[0].value
    # The panel is usable again afterwards.
    assert panel._button.enabled
    assert not panel._cancel.visible
